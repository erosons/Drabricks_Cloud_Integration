"""Soak tool: validate the Databento live feed end to end, read-only.

Connects with DATABENTO_API_KEY (env or ../.env), subscribes trades +
mbp-1 for one raw CME symbol through the SAME DatabentoFeed translation
the bot uses, listens briefly, and reports what the engine would have
seen: book updates, trades by aggressor side, best bid/ask. Optionally
captures every raw record to a text log for shape verification.

    python scripts/check_live_feed.py                     # front-month MESU6
    python scripts/check_live_feed.py --symbol MNQU6 --listen 60
    python scripts/check_live_feed.py --capture logs/live_feed.txt

Exit codes: 0 data flowed, 2 key missing/rejected or subscription
refused, 4 connected but no market data arrived (check Globex hours:
halt 17:00–18:00 ET, closed Saturday).
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_data.databento_feed import DatabentoFeed
from src.market_data.orderbook import OrderBook
from src.utils.logger import get_logger

log = get_logger("live_feed_check")


def load_key() -> str | None:
    key = os.environ.get("DATABENTO_API_KEY")
    if not key and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("DATABENTO_API_KEY="):
                key = line.split("=", 1)[1].strip()
    return key


async def amain() -> int:
    parser = argparse.ArgumentParser(description="validate Databento live feed")
    parser.add_argument("--symbol", default="MESU6",
                        help="raw CME contract symbol (default MESU6)")
    parser.add_argument("--dataset", default="GLBX.MDP3")
    parser.add_argument("--listen", type=int, default=30,
                        help="seconds to consume live events (default 30)")
    parser.add_argument("--capture", default=None,
                        help="append every raw record to this file")
    args = parser.parse_args()

    key = load_key()
    if not key:
        log.error("DATABENTO_API_KEY not set (env or .env)")
        return 2

    counts: collections.Counter = collections.Counter()
    first: dict[str, str] = {}

    book = OrderBook(args.symbol, 0.25)

    async def on_book_update() -> None:
        counts["book_updates"] += 1

    async def on_trade(price: float, size: float, side: str) -> None:
        counts[f"trades_{side}"] += 1
        first.setdefault("trade",
                         f"price={price} size={size} side={side}")

    feed = DatabentoFeed(api_key=key, dataset=args.dataset,
                         symbol=args.symbol, book=book,
                         on_book_update=on_book_update, on_trade=on_trade)

    if args.capture:
        cap = open(args.capture, "a")
        inner = feed.dispatch

        async def capturing_dispatch(rec) -> None:
            cap.write(f"{type(rec).__name__} {rec}\n")
            counts[type(rec).__name__] += 1
            first.setdefault(type(rec).__name__, str(rec)[:300])
            await inner(rec)
        feed.dispatch = capturing_dispatch  # type: ignore[method-assign]

    stop = asyncio.Event()

    async def timer() -> None:
        await asyncio.sleep(args.listen)
        stop.set()

    timer_task = asyncio.create_task(timer())
    log.info("listening %ds for %s on %s…", args.listen, args.symbol,
             args.dataset)
    rc = await feed.run(stop)
    timer_task.cancel()
    if args.capture:
        cap.close()
        log.info("raw records appended to %s", args.capture)

    for name, snippet in first.items():
        log.info("first %s: %s", name, snippet)
    log.info("counts over %ds: %s", args.listen, dict(counts))
    log.info("book at end: bid=%s ask=%s synced=%s",
             book.best_bid(), book.best_ask(), book.synced)

    if rc != 0:
        return 2
    if feed.md_records == 0:
        log.warning("connected but no market data arrived — check whether "
                    "the market is open (Globex halt 17:00–18:00 ET, closed "
                    "Saturday) before reading anything into it")
        return 4
    log.info("live feed verified ✓ (%d md records)", feed.md_records)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(amain()))
    except KeyboardInterrupt:
        sys.exit(0)
