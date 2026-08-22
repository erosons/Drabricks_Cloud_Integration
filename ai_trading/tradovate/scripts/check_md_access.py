"""Soak tool: validate market-data entitlement, read-only.

Authenticates, checks the auth response for mdAccessToken (Market Data
scope on the API key), opens the MD socket, and tries md/subscribeQuote +
md/subscribeDOM for one symbol. Then listens briefly and counts the live
quote/DOM events that arrive, and unsubscribes. Sends no orders.

    python scripts/check_md_access.py                    # front-month MESU6
    python scripts/check_md_access.py --symbol MNQU6
    python scripts/check_md_access.py --listen 30        # listen 30s

Exit codes: 0 subscriptions accepted, 2 auth failed, 3 no mdAccessToken
(Market Data scope missing on the key), 4 subscribe refused ("Symbol is
inaccessible" = market-data/API add-on subscription missing on the
account — not a symbol-format problem, see docs/API-document.md).
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp

from src.auth.tradovate_auth import AuthError
from src.client.gateway import Gateway
from src.client.websocket import TradovateSocket
from src.config_loader import load_config
from src.utils.logger import get_logger

log = get_logger("md_check")


async def amain() -> int:
    parser = argparse.ArgumentParser(description="validate market-data access")
    parser.add_argument("--config-dir",
                        default=str(Path(__file__).resolve().parents[1] / "config"))
    parser.add_argument("--symbol", default="MESU6")
    parser.add_argument("--listen", type=int, default=15,
                        help="seconds to count live events (default 15)")
    args = parser.parse_args()

    config = load_config(args.config_dir)
    counts: collections.Counter = collections.Counter()
    first: dict = {}

    def on_event(msg) -> None:
        if not isinstance(msg, dict):
            return
        for key in ("quotes", "doms", "charts", "histograms"):
            if key in (msg.get("d") or {}):
                counts[key] += 1
                if key not in first:
                    first[key] = msg
                return
        counts["other"] += 1

    async with aiohttp.ClientSession() as http:
        try:
            gateway = Gateway(config, http)
            await gateway.start()
        except AuthError as exc:
            log.error("%s", exc)
            return 2
        sock = None
        try:
            md_token = gateway.auth.token.md_access_token
            if not md_token:
                log.error("auth response carried no mdAccessToken — the API "
                          "key lacks the Market Data scope")
                return 3
            log.info("mdAccessToken present ✓")

            found = await gateway.request(
                "GET", f"contract/find?name={args.symbol}")
            log.info("contract/find %s → %s", args.symbol,
                     json.dumps(found)[:200])

            sock = TradovateSocket(config.raw["tradovate"]["market_data_ws"],
                                   md_token, on_event=on_event, name="md")
            await sock.connect()
            log.info("MD socket authorized ✓")

            refused = False
            for endpoint in ("md/subscribeQuote", "md/subscribeDOM"):
                resp = await sock.request(endpoint, body={"symbol": args.symbol})
                d = resp.get("d")
                d = d if isinstance(d, dict) else {}
                # refusals come back s=200 with the error inside d:
                #   {"errorText": "Symbol is inaccessible",
                #    "errorCode": "UnknownSymbol", "mode": "None"}
                if resp.get("s") == 200 and not d.get("errorText") \
                        and d.get("mode") != "None":
                    log.info("%s %s → accepted ✓ mode=%s", endpoint,
                             args.symbol, d.get("mode"))
                else:
                    refused = True
                    log.error("%s %s REFUSED: s=%s d=%s", endpoint,
                              args.symbol, resp.get("s"), json.dumps(d)[:300])
            if refused:
                log.error("entitlement missing — enable the market-data/API "
                          "add-on for the account (docs/API-document.md)")
                return 4

            log.info("listening %ds for live events…", args.listen)
            await asyncio.sleep(args.listen)
            for key, msg in first.items():
                log.info("first %s frame: %s", key, json.dumps(msg)[:400])
            log.info("event counts over %ds: %s", args.listen, dict(counts))
            if not counts:
                log.warning("subscriptions accepted but no events arrived — "
                            "check whether the market is open (Globex halt "
                            "17:00–18:00 ET) before reading anything into it")

            for endpoint in ("md/unsubscribeQuote", "md/unsubscribeDOM"):
                await sock.request(endpoint, body={"symbol": args.symbol})
        finally:
            if sock is not None:
                await sock.close()
            await gateway.stop()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(amain()))
    except KeyboardInterrupt:
        sys.exit(0)
