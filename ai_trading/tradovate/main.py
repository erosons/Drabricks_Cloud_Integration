"""Single-product entrypoint (§18-§19).

    python main.py --product MES               # live market data (needs creds)
    python main.py --product MES --synthetic   # offline synthetic feed, dry_run only

Wires: config contracts → DB → session manager → news guard → contract
staleness gate → lifecycle gate → order-flow engine → executor.

dry_run: true (config default) = signals only, orders go nowhere. The
--synthetic flag replaces the MD websocket with a bounded random-walk feed
so the whole pipeline can be exercised with no credentials and no network —
it refuses to run unless mode is DRY_RUN.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from pathlib import Path

from src.config_loader import AppConfig, ExecutionMode, load_config
from src.market_data.orderbook import OrderBook
from src.reference.contract_resolver import is_tradeable
from src.scheduling.news_guard import NewsGuard
from src.scheduling.session_manager import SessionManager
from src.storage.db import Database, utc_now_iso
from src.trading.order_flow import (
    DryRunExecutor,
    FuturesOrderFlowStrategy,
    OrderFlowAnalyzer,
)
from src.trading.price_action import PriceActionAnalyzer
from src.trading.position import PositionTracker
from src.trading.risk import RiskManager
from src.utils.logger import get_logger

log = get_logger("main")

STRATEGY = "order_flow_scalp"      # the only enabled module (config)


def seed_legacy_lifecycle(db: Database, product: str) -> None:
    """order_flow_scalp predates the lifecycle and is live-by-default (its
    card says so explicitly) — seed a 'live' row ONCE so gate F4 passes,
    loudly, until it is run backwards through G2–G4."""
    row = db.conn.execute(
        "SELECT state FROM strategy_lifecycle WHERE strategy=? AND product=? "
        "ORDER BY id DESC LIMIT 1", (STRATEGY, product)).fetchone()
    if row is None:
        db.conn.execute(
            "INSERT INTO strategy_lifecycle (strategy, product, state, entered_state_at)"
            " VALUES (?,?,?,?)", (STRATEGY, product, "live", utc_now_iso()))
        log.warning("[%s] seeded LEGACY live-by-default lifecycle row for %s — "
                    "must be run backwards through G2-G4 (card prerequisite)",
                    product, STRATEGY)


def lifecycle_state(db: Database, product: str) -> str | None:
    row = db.conn.execute(
        "SELECT state FROM strategy_lifecycle WHERE strategy=? AND product=? "
        "ORDER BY id DESC LIMIT 1", (STRATEGY, product)).fetchone()
    return row["state"] if row else None


def build_engine(config: AppConfig, db: Database, product_symbol: str,
                 contract_symbol: str) -> FuturesOrderFlowStrategy:
    product = config.products[product_symbol]
    params = config.strategies[STRATEGY].params
    stale_hours = float(config.raw["contract_resolver"]["stale_after_hours"])

    engine = FuturesOrderFlowStrategy(
        product=product,
        contract_symbol=contract_symbol,
        analyzer=OrderFlowAnalyzer(
            imbalance_threshold=params["imbalance_threshold"],
            book_depth=params["book_depth"],
            min_confidence=params["min_confidence"],
        ),
        price_action=PriceActionAnalyzer(
            fast_period=params["fast_ema"],
            slow_period=params["slow_ema"],
            spike_threshold=params["spike_threshold"],
            recovery_pct=params["recovery_pct"],
            exhaustion_ttl=params["exhaustion_ttl"],
            retest_proximity=params["retest_proximity"],
            retest_memory_ticks=params["retest_memory_ticks"],
            retest_ttl=params["retest_ttl"],
        ),
        risk_manager=RiskManager(product),
        position_tracker=PositionTracker(product.tick_size, product.tick_value),
        executor=DryRunExecutor(product_symbol),
        session_manager=SessionManager(config.raw["session"]),
        news_guard=NewsGuard(db, config.raw["news_guard"]),
        lifecycle_ok=lambda: lifecycle_state(db, product_symbol) in ("live", "incubation"),
        contract_fresh=lambda: is_tradeable(db, product_symbol, stale_hours),
        max_spread_ticks=params["max_spread_ticks"],
    )
    book = OrderBook(contract_symbol, product.tick_size)
    engine.attach_orderbook(book)
    return engine


async def run_synthetic(engine: FuturesOrderFlowStrategy, ticks: int) -> None:
    """Bounded random-walk DOM + trades through the full pipeline."""
    tick = engine.product.tick_size
    mid = 6400 * tick if tick >= 1 else 6400.0
    rng = random.Random(42)
    for i in range(ticks):
        mid = mid + rng.choice([-1, 0, 0, 1]) * tick
        depth = [
            {"price": mid - (k + 0.5) * tick, "size": rng.randint(5, 80)}
            for k in range(10)
        ]
        engine.book.apply_dom({
            "bids": depth,
            "asks": [{"price": mid + (k + 0.5) * tick, "size": rng.randint(5, 80)}
                     for k in range(10)],
        })
        await engine.on_book_update()
        if i % 3 == 0:
            await engine.on_trade(mid, rng.randint(1, 5),
                                  rng.choice(["buy", "sell"]))
    log.info("synthetic feed done: %d ticks | gate skips: %s | dry-run entries: %d",
             ticks, engine.skips,
             len(getattr(engine.executor, "entries", [])))


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Tradovate bot — one product")
    parser.add_argument("--product", required=True)
    parser.add_argument("--config-dir", default=str(Path(__file__).parent / "config"))
    parser.add_argument("--synthetic", action="store_true",
                        help="offline random-walk feed (dry_run mode only)")
    parser.add_argument("--ticks", type=int, default=2000)
    args = parser.parse_args()

    os.environ.setdefault("BOT_PRODUCT", args.product)
    config = load_config(args.config_dir)

    if args.product not in config.products:
        log.error("unknown product %s", args.product)
        return 2
    product = config.products[args.product]

    db = Database(Path(args.config_dir).parent / config.raw["database"]["path"])
    seed_legacy_lifecycle(db, args.product)

    # F3: active contract must exist and be fresh — synthetic mode fabricates one
    active = db.get_active_contract(args.product)
    if args.synthetic and active is None:
        db.upsert_active_contract(args.product, f"{args.product}U6", "SEP 2026",
                                  "2026-08-14", 1, 1)
        active = db.get_active_contract(args.product)
    if active is None:
        log.error("no active contract for %s — run the reference daemon first "
                  "(python -m src.reference.contract_resolver --once)", args.product)
        return 2

    engine = build_engine(config, db, args.product, active["contract_code"])

    if args.synthetic:
        if config.mode is not ExecutionMode.DRY_RUN:
            log.error("--synthetic requires dry_run: true")
            return 2
        await run_synthetic(engine, args.ticks)
        return 0

    if config.mode is ExecutionMode.DRY_RUN:
        log.info("mode: DRY RUN — live market data, signals only")
    # Live/demo market-data path: gateway + MD websocket (Phase 7/8 wiring —
    # requires TRADOVATE_* credentials; see docs/API-document.md)
    from src.auth.tradovate_auth import Credentials  # fails fast with clear msg
    Credentials.from_env()
    log.error("live MD streaming loop lands with the launcher (Phase 7); "
              "use --synthetic for the offline pipeline until then")
    return 3


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
