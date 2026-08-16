"""THE single Tradovate session (§17 attestation #19, §18).

One gateway per deployment owns the token and the websockets; every product
process goes through it. (Prototype phase: the gateway lives in-process and
the local-RPC fan-out arrives with the multi-product launcher — Phase 7.)

Rate discipline (attestation #21–23):
  * token-bucket budgeter kept at ≥20% headroom under the published caps —
    caps may change without notice, so the budget is config-overridable
  * HTTP 429 → exponential backoff
  * p-ticket/p-time penalties → persisted to disk and replayed after the
    prescribed wait, so a crash-restart cannot hot-loop an endpoint
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import aiohttp

from src.auth.tradovate_auth import (
    Credentials,
    TradovateAuth,
    parse_penalty,
)
from src.config_loader import AppConfig
from src.auth import tradovate_auth

log = logging.getLogger("gateway")


class GatewayError(Exception):
    pass


class TokenBucket:
    """Sustained-rate limiter: `rate` requests/second, burst up to `capacity`."""

    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self._tokens = float(capacity)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.capacity,
                                   self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) / self.rate)


class PenaltyStore:
    """Unexpired penalty tickets on disk — replayed across restarts."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        tickets = json.loads(self.path.read_text())
        return {ep: t for ep, t in tickets.items()
                if t["retry_at"] > time.time()}

    def record(self, endpoint: str, ticket: str, penalty_seconds: float) -> None:
        tickets = self.load()
        tickets[endpoint] = {"ticket": ticket,
                             "retry_at": time.time() + penalty_seconds}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(tickets))

    def clear(self, endpoint: str) -> None:
        tickets = self.load()
        if endpoint in tickets:
            del tickets[endpoint]
            self.path.write_text(json.dumps(tickets))

    def pending(self, endpoint: str) -> dict | None:
        return self.load().get(endpoint)


class Gateway:
    """request() = budgeted, penalty-aware, 429-backoff REST call."""

    def __init__(self, config: AppConfig, session: aiohttp.ClientSession,
                 credentials: Credentials | None = None,
                 penalty_path: str | Path | None = None):
        gw_cfg = config.raw.get("gateway", {})
        self.base_url = tradovate_auth.rest_base_url(config)
        self.session = session
        self.auth = TradovateAuth(
            config, credentials or Credentials.from_env(), session)
        self.bucket = TokenBucket(
            rate=float(gw_cfg.get("requests_per_second", 2.0)),
            capacity=int(gw_cfg.get("burst", 5)),
        )
        db_path = Path(config.raw["database"]["path"])
        self.penalties = PenaltyStore(
            penalty_path or db_path.parent / "penalty_tickets.json")
        self.max_429_retries = int(gw_cfg.get("max_429_retries", 5))

    async def start(self) -> None:
        await self.auth.authenticate()
        self._renewal = asyncio.create_task(
            self.auth.renewal_loop(), name="token-renewal")

    async def stop(self) -> None:
        if getattr(self, "_renewal", None):
            self._renewal.cancel()

    async def request(self, method: str, endpoint: str,
                      body: dict | None = None) -> dict | list:
        """POST/GET {base}/{endpoint}. Applies: pending-penalty wait+replay,
        rate budget, 429 exponential backoff, new-penalty persistence."""
        body = dict(body or {})

        pending = self.penalties.pending(endpoint)
        if pending is not None:
            wait = max(0.0, pending["retry_at"] - time.time())
            log.warning("%s: pending penalty ticket — waiting %.0fs", endpoint, wait)
            await asyncio.sleep(wait)
            body["p-ticket"] = pending["ticket"]

        backoff = 1.0
        for attempt in range(self.max_429_retries + 1):
            await self.bucket.acquire()
            async with self.session.request(
                    method, f"{self.base_url}/{endpoint.lstrip('/')}",
                    json=body if method == "POST" else None,
                    headers=self.auth.auth_header()) as resp:
                if resp.status == 429:
                    log.warning("%s: 429 — backing off %.1fs", endpoint, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
                    continue
                payload = await resp.json(content_type=None)

            if isinstance(payload, dict):
                penalty = parse_penalty(payload)
                if penalty is not None:
                    self.penalties.record(endpoint, penalty.ticket,
                                          penalty.penalty_seconds)
                    if penalty.captcha:
                        raise GatewayError(
                            f"{endpoint}: captcha penalty — manual intervention")
                    log.warning("%s: penalty — waiting %.0fs then replaying",
                                endpoint, penalty.penalty_seconds)
                    await asyncio.sleep(penalty.penalty_seconds)
                    body["p-ticket"] = penalty.ticket
                    continue

            self.penalties.clear(endpoint)
            return payload

        raise GatewayError(f"{endpoint}: exhausted retries")
