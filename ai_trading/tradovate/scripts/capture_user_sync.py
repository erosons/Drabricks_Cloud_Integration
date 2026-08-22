"""Soak tool: capture RAW user/syncrequest events, verbatim, to close the ⚠
in docs/API-document.md (user-data event shapes unverified on demo).

Sends NO orders and modifies NOTHING. While it runs, place / cancel / fill a
minimal order manually in the Tradovate demo UI; every frame the trading
socket delivers is appended as one JSON line to
logs/user_sync_capture_<UTC>.jsonl. Afterwards, reconcile the captured
shapes against the assumptions in src/trading/user_sync.py, turn real
frames into test fixtures, and flip the doc to "✓ verified on demo".

    python scripts/capture_user_sync.py                 # 15 min capture
    python scripts/capture_user_sync.py --duration 300  # 5 min

Needs TRADOVATE_* credentials; exits 3 with a permission hint if
user/syncrequest is denied (the API key needs the User Data category).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp

from src.auth.tradovate_auth import AuthError, trading_ws_url
from src.client.gateway import Gateway
from src.client.rest import TradovateREST
from src.client.websocket import TradovateSocket
from src.config_loader import ExecutionMode, load_config
from src.utils.logger import get_logger

log = get_logger("capture")


async def amain() -> int:
    parser = argparse.ArgumentParser(description="capture user/syncrequest events")
    parser.add_argument("--config-dir",
                        default=str(Path(__file__).resolve().parents[1] / "config"))
    parser.add_argument("--duration", type=int, default=900,
                        help="capture window in seconds (default 900)")
    args = parser.parse_args()

    config = load_config(args.config_dir)
    if config.mode is ExecutionMode.LIVE:
        log.warning("config selects the LIVE endpoint — captured events will "
                    "be from the LIVE account")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(__file__).resolve().parents[1] / "logs" / f"user_sync_capture_{stamp}.jsonl"
    out.parent.mkdir(exist_ok=True)
    fh = out.open("w")

    def record(kind: str, payload) -> None:
        line = json.dumps({"kind": kind, "at": datetime.now(timezone.utc).isoformat(),
                           "payload": payload})
        fh.write(line + "\n")
        fh.flush()
        log.info("%s: %s", kind, json.dumps(payload)[:400])

    async with aiohttp.ClientSession() as http:
        try:
            gateway = Gateway(config, http)
            await gateway.start()
        except AuthError as exc:
            log.error("%s", exc)
            return 2
        sock = None
        try:
            accounts = await TradovateREST(gateway).account_list()
            record("account_list", accounts)
            user_ids = sorted({a["userId"] for a in accounts
                               if isinstance(a, dict) and "userId" in a})
            if not user_ids:
                log.error("no userId in account/list — cannot syncrequest")
                return 3

            sock = TradovateSocket(trading_ws_url(config),
                                   gateway.auth.token.access_token,
                                   on_event=lambda msg: record("event", msg),
                                   name="capture")
            await sock.connect()
            sync = await sock.request("user/syncrequest", body={"users": user_ids})
            record("syncrequest_response", sync)
            if sync.get("s") != 200:
                log.error("user/syncrequest DENIED (s=%s) — grant the User Data "
                          "permission category on the API key, then rerun",
                          sync.get("s"))
                return 3

            log.info("capturing for %ds → %s", args.duration, out)
            log.info(">>> now place / cancel / fill a MINIMAL order manually "
                     "in the Tradovate UI <<<")
            try:
                await asyncio.sleep(args.duration)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
        finally:
            if sock is not None:
                await sock.close()
            await gateway.stop()
            fh.close()
            log.info("capture written: %s", out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(amain()))
    except KeyboardInterrupt:
        sys.exit(0)
