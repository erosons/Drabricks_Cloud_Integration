"""Single-product entrypoint (§18-§19).

    python main.py --product MES               # live market data (needs creds)
    python main.py --product MES --synthetic   # offline synthetic feed, dry_run only

Wires: config contracts → DB → session manager → news guard → contract
staleness gate → lifecycle gate → order-flow engine → executor.

dry_run: true (config default) = signals only, orders go nowhere. Without
--synthetic this streams REAL market data (Databento live GLBX.MDP3 →
DatabentoFeed → engine) through the full pipeline — needs only
DATABENTO_API_KEY, no Tradovate credentials. The --synthetic flag replaces
the live feed with a bounded random-walk so the whole pipeline can be
exercised with no credentials and no network — it refuses to run unless
mode is DRY_RUN.

dry_run: false = the same MD loop plus the order path: trading socket with
user/syncrequest fill routing and LiveExecutor sending real OSO brackets to
the demo (live_trading: false) or LIVE (live_trading: true) account. Refuses
to start if user/syncrequest is denied (never trade blind) or the account
already holds a position in the contract.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import signal as signal_module
import sys
from pathlib import Path

import aiohttp

from src.auth.tradovate_auth import AuthError, trading_ws_url
from src.client.gateway import Gateway
from src.client.rest import TradovateREST
from src.client.websocket import TradovateSocket
from src.config_loader import AppConfig, ExecutionMode, load_config
from src.market_data.databento_feed import DatabentoFeed
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
from src.trading.live_executor import LiveExecutor
from src.trading.price_action import PriceActionAnalyzer
from src.trading.position import PositionTracker
from src.trading.risk import RiskManager
from src.trading.user_sync import UserSyncRouter
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


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def _md_loop(config: AppConfig, engine, stop: asyncio.Event) -> int:
    """Reconnecting live MD stream: Databento GLBX.MDP3 → DatabentoFeed →
    engine callbacks. Gaps/disconnects are drop-and-resync (§17
    attestation #24–25). Tradovate MD needs a CME ILA sub-vendor license
    (docs/API-document.md) — market data comes from Databento instead."""
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        log.error("DATABENTO_API_KEY not set — the live feed needs a "
                  "Databento key with an active CME (GLBX.MDP3) subscription")
        return 3
    feed = DatabentoFeed(
        api_key=api_key,
        dataset=config.raw["databento"]["dataset"],
        symbol=engine.contract_symbol,
        book=engine.book,
        on_book_update=engine.on_book_update,
        on_trade=engine.on_trade,
    )
    return await feed.run(stop)


async def _attach_order_path(config: AppConfig, engine, gateway: Gateway,
                             stop: asyncio.Event, db: Database):
    """dry_run: false — wire the orders-out side: account + contract lookup,
    trading socket with user/syncrequest fill routing, LiveExecutor.
    Returns (exit_code, trading_socket|None, background_tasks)."""
    rest = TradovateREST(gateway)

    accounts = await rest.account_list()
    active = [a for a in accounts
              if isinstance(a, dict) and a.get("active", True)]
    if not active:
        log.error("no active account in account/list: %s", accounts)
        return 3, None, []
    acct = active[0]

    found = await gateway.request(
        "GET", f"contract/find?name={engine.contract_symbol}")
    if isinstance(found, list):
        found = found[0] if found else None
    contract_id = found.get("id") if isinstance(found, dict) else None
    if contract_id is None:
        log.error("contract/find could not resolve %s: %s",
                  engine.contract_symbol, found)
        return 3, None, []

    queue: asyncio.Queue = asyncio.Queue()
    sock = TradovateSocket(trading_ws_url(config),
                           gateway.auth.token.access_token,
                           on_event=queue.put_nowait, name="trading")
    await sock.connect()
    sync = await sock.request("user/syncrequest",
                              body={"users": [acct["userId"]]})
    if sync.get("s") != 200:
        log.error("user/syncrequest denied (%s) — the API key needs the User "
                  "Data permission (docs/API-document.md); refusing to trade "
                  "without fill confirmations", sync)
        await sock.close()
        return 3, None, []

    # never start into an existing position — engine assumes a flat book
    snapshot = sync.get("d") or {}
    for pos in snapshot.get("positions", []):
        if pos.get("contractId") == contract_id and pos.get("netPos"):
            log.error("account %s already holds netPos=%s in %s — flatten "
                      "manually before starting", acct.get("name"),
                      pos.get("netPos"), engine.contract_symbol)
            await sock.close()
            return 3, None, []

    executor = LiveExecutor(
        rest, account_spec=acct["name"], account_id=acct["id"],
        contract_id=contract_id, product=engine.product.symbol)

    async def on_fill(side, qty, price, fee=0.0):
        executor.note_fill(side, qty)   # releases the one-bracket guard
        # of-record trail (§15/§16): every broker fill lands in SQLite;
        # v_round_trips derives win/loss history from these rows
        db.record_fill(engine.product.symbol, engine.contract_symbol,
                       side, qty, price, fee)
        await engine.on_fill(side, qty, price, fee)

    router = UserSyncRouter(contract_id, on_fill, engine.on_order_nack)

    async def pump() -> None:
        while True:
            await router.route(await queue.get())

    async def watchdog() -> None:
        # fills gone = flying blind; stop the bot (server-side bracket stop
        # still protects any open position)
        while not stop.is_set():
            if not sock.connected.is_set():
                log.critical("trading socket lost — stopping")
                stop.set()
                return
            await asyncio.sleep(1.0)

    tasks = [asyncio.create_task(pump(), name="user-sync-pump"),
             asyncio.create_task(watchdog(), name="trading-ws-watchdog")]

    engine.executor = executor
    log.info("order path armed: account=%s (%s) contract=%s (id=%s)",
             acct["name"], acct["id"], engine.contract_symbol, contract_id)
    return 0, sock, tasks


async def run_live(config: AppConfig, engine, db: Database) -> int:
    """Live market data (Databento) for every non-synthetic mode; live
    order routing (Tradovate) when dry_run: false."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal_module.SIGINT, signal_module.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    if config.mode is ExecutionMode.DRY_RUN:
        # signals only — no orders, so no Tradovate connection at all
        log.info("mode: DRY RUN — live Databento market data, signals only")
        return await _md_loop(config, engine, stop)

    async with aiohttp.ClientSession() as http:
        gateway = Gateway(config, http)
        await gateway.start()
        trade_sock, tasks = None, []
        try:
            if config.mode is ExecutionMode.LIVE:
                log.warning("mode: LIVE — orders go to the LIVE account "
                            "with REAL MONEY")
            else:
                log.info("mode: DEMO — orders go to the demo account")
            rc, trade_sock, tasks = await _attach_order_path(
                config, engine, gateway, stop, db)
            if rc != 0:
                return rc
            return await _md_loop(config, engine, stop)
        finally:
            for task in tasks:
                task.cancel()
            if trade_sock is not None:
                await trade_sock.close()
            await gateway.stop()


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

    metrics_port = os.environ.get("METRICS_PORT")
    if metrics_port and not args.synthetic:
        from src.utils.metrics import start_metrics_server
        start_metrics_server(int(metrics_port))

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

    try:
        return await run_live(config, engine, db)
    except AuthError as exc:
        log.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
