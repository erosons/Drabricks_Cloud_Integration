"""Tradovate authentication — access token request + renewal (§18, docs/API-document.md).

Credentials come from environment variables only (§21): TRADOVATE_USERNAME,
TRADOVATE_PASSWORD, TRADOVATE_APP_ID, TRADOVATE_CID, TRADOVATE_SECRET,
TRADOVATE_DEVICE_ID. Endpoint (demo vs live) is selected from the mode
switches — never passed in by callers.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiohttp

from src.config_loader import AppConfig, ExecutionMode

log = logging.getLogger("tradovate_auth")

ENV_VARS = ("TRADOVATE_USERNAME", "TRADOVATE_PASSWORD", "TRADOVATE_APP_ID",
            "TRADOVATE_CID", "TRADOVATE_SECRET", "TRADOVATE_DEVICE_ID")


class AuthError(Exception):
    pass


class PenaltyResponse(Exception):
    """A p-ticket/p-time response. Caller waits penalty_seconds and retries
    with `ticket` in the body; captcha means a bot cannot resolve it."""

    def __init__(self, ticket: str, penalty_seconds: float, captcha: bool):
        self.ticket = ticket
        self.penalty_seconds = penalty_seconds
        self.captcha = captcha
        super().__init__(f"time penalty: wait {penalty_seconds}s"
                         + (" (captcha — unresolvable by bot)" if captcha else ""))


@dataclass(frozen=True)
class Credentials:
    name: str
    password: str
    app_id: str
    cid: int
    sec: str
    device_id: str
    app_version: str = "1.0"

    @classmethod
    def from_env(cls) -> "Credentials":
        missing = [v for v in ENV_VARS if not os.environ.get(v)]
        if missing:
            raise AuthError(f"missing credential env vars: {missing}")
        return cls(
            name=os.environ["TRADOVATE_USERNAME"],
            password=os.environ["TRADOVATE_PASSWORD"],
            app_id=os.environ["TRADOVATE_APP_ID"],
            cid=int(os.environ["TRADOVATE_CID"]),
            sec=os.environ["TRADOVATE_SECRET"],
            device_id=os.environ["TRADOVATE_DEVICE_ID"],
        )

    def request_body(self) -> dict:
        return {
            "name": self.name, "password": self.password,
            "appId": self.app_id, "appVersion": self.app_version,
            "cid": self.cid, "sec": self.sec, "deviceId": self.device_id,
        }


@dataclass
class Token:
    access_token: str
    md_access_token: str | None
    expiration: datetime

    def expires_within(self, delta: timedelta) -> bool:
        return datetime.now(timezone.utc) + delta >= self.expiration


def rest_base_url(config: AppConfig) -> str:
    tv = config.raw["tradovate"]
    return tv["live_rest"] if config.mode is ExecutionMode.LIVE else tv["demo_rest"]


def trading_ws_url(config: AppConfig) -> str:
    tv = config.raw["tradovate"]
    return tv["live_ws"] if config.mode is ExecutionMode.LIVE else tv["demo_ws"]


def parse_penalty(payload: dict) -> PenaltyResponse | None:
    if "p-ticket" in payload:
        return PenaltyResponse(
            ticket=payload["p-ticket"],
            penalty_seconds=float(payload.get("p-time", 60)),
            captcha=bool(payload.get("p-captcha", False)),
        )
    return None


def parse_token_response(payload: dict) -> Token:
    penalty = parse_penalty(payload)
    if penalty is not None:
        raise penalty
    if "accessToken" not in payload:
        raise AuthError(f"unexpected auth response: {payload}")
    return Token(
        access_token=payload["accessToken"],
        md_access_token=payload.get("mdAccessToken"),
        expiration=datetime.fromisoformat(
            payload["expirationTime"].replace("Z", "+00:00")),
    )


class TradovateAuth:
    """Owns the token for the process (used only by the gateway — §17 #19)."""

    def __init__(self, config: AppConfig, credentials: Credentials,
                 session: aiohttp.ClientSession):
        self.base_url = rest_base_url(config)
        self.credentials = credentials
        self.session = session
        self.renew_after = timedelta(
            minutes=int(config.raw["tradovate"]["token_renewal_minutes"]))
        self.token: Token | None = None

    async def authenticate(self, max_penalty_retries: int = 3) -> Token:
        body = self.credentials.request_body()
        for _ in range(max_penalty_retries + 1):
            async with self.session.post(
                    f"{self.base_url}/auth/accesstokenrequest", json=body) as resp:
                payload = await resp.json()
            try:
                self.token = parse_token_response(payload)
                log.info("authenticated; token expires %s", self.token.expiration)
                return self.token
            except PenaltyResponse as penalty:
                if penalty.captcha:
                    raise
                log.warning("auth penalty — waiting %.0fs", penalty.penalty_seconds)
                await asyncio.sleep(penalty.penalty_seconds)
                body = {**body, "p-ticket": penalty.ticket}
        raise AuthError("auth failed after penalty retries")

    async def renew(self) -> Token:
        assert self.token is not None
        async with self.session.get(
                f"{self.base_url}/auth/renewaccesstoken",
                headers=self.auth_header()) as resp:
            payload = await resp.json()
        penalty = parse_penalty(payload)
        if penalty is not None:
            raise penalty
        if "expirationTime" in payload:
            self.token.expiration = datetime.fromisoformat(
                payload["expirationTime"].replace("Z", "+00:00"))
            if payload.get("accessToken"):
                self.token.access_token = payload["accessToken"]
            log.info("token renewed; expires %s", self.token.expiration)
            return self.token
        raise AuthError(f"unexpected renewal response: {payload}")

    async def renewal_loop(self) -> None:
        """Background task: renew every token_renewal_minutes; on failure,
        full re-auth (tokens die at ~90 min so there is slack for one retry)."""
        while True:
            await asyncio.sleep(self.renew_after.total_seconds())
            try:
                await self.renew()
            except (PenaltyResponse, AuthError, aiohttp.ClientError) as exc:
                log.error("renewal failed (%s) — re-authenticating", exc)
                await self.authenticate()

    def auth_header(self) -> dict[str, str]:
        assert self.token is not None, "authenticate() first"
        return {"Authorization": f"Bearer {self.token.access_token}"}
