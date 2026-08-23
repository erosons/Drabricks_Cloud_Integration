"""Monday market rehearsal: momentum_dollar_trail on the Tradovate DEMO
account with live Databento data. Plan: plan/plan.md.

    python scripts/demo_momentum_trail.py                # MES, demo account

REFUSES to run with live_trading: true — this strategy has not passed the
gates; the rehearsal is for order-path verification and live-vs-sim fill
comparison only. Requires mode.dry_run: false (orders must actually reach
the demo account) and DATABENTO_API_KEY + TRADOVATE_* in the environment.
"""

from __future__ import annotations

import asyncio
import os
import signal as signal_module
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import aiohttp

from main import _attach_order_path
from src.auth.tradovate_auth import AuthError
from src.client.gateway import Gateway
from src.config_loader import ExecutionMode, load_config
from src.market_data.databento_feed import DatabentoFeed
from src.market_data.orderbook import OrderBook
from src.scheduling.session_manager import SessionManager
from src.storage.db import Database
from src.trading.trail_runner import TrailRunner
from src.utils.logger import get_logger

log = get_logger("demo_trail")


async def amain() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Monday demo rehearsal")
    parser.add_argument("--product", default="MES")
    parser.add_argument("--config-dir", default=str(ROOT / "config"))
    args = parser.parse_args()

    config = load_config(args.config_dir)
    if config.mode is ExecutionMode.LIVE:
        log.error("REFUSED: live_trading is true — this strategy is not "
                  "gate-approved (plan/plan.md); demo account only")
        return 2
    if config.mode is ExecutionMode.DRY_RUN:
        log.error("mode.dry_run is true — the rehearsal needs orders to "
                  "reach the DEMO account; set dry_run: false "
                  "(live_trading stays false)")
        return 2
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        log.error("DATABENTO_API_KEY not set")
        return 2

    db = Database(ROOT / config.raw["database"]["path"])
    active = db.get_active_contract(args.product)
    if active is None:
        log.error("no active contract for %s — run the resolver first",
                  args.product)
        return 2
    contract_symbol = active["contract_code"]
    product = config.products[args.product]
    params = config.strategies["momentum_dollar_trail"].params

    runner = TrailRunner(product, contract_symbol, params,
                         SessionManager(config.raw["session"]))
    log.warning("MONDAY REHEARSAL: %s on DEMO — pure %g-pt trail, "
                "init stop %g pts, 1 contract, flatten 15:55 ET",
                contract_symbol, runner.trail, runner.init_dist)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal_module.SIGINT, signal_module.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async with aiohttp.ClientSession() as http:
        gateway = Gateway(config, http)
        await gateway.start()
        trade_sock, tasks = None, []
        try:
            rc, trade_sock, tasks = await _attach_order_path(
                config, runner, gateway, stop, db)
            if rc != 0:
                return rc
            book = OrderBook(contract_symbol, product.tick_size)

            async def on_book_update() -> None:
                pass                                   # trail is trade-driven

            feed = DatabentoFeed(
                api_key=api_key,
                dataset=config.raw["databento"]["dataset"],
                symbol=contract_symbol, book=book,
                on_book_update=on_book_update,
                on_trade=runner.on_trade)
            rc = await feed.run(stop)
            log.info("rehearsal stats: %s", runner.stats)
            return rc
        except AuthError as exc:
            log.error("%s", exc)
            return 2
        finally:
            for task in tasks:
                task.cancel()
            if trade_sock is not None:
                await trade_sock.close()
            await gateway.stop()


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
