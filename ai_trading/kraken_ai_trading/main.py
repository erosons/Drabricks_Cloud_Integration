"""
Kraken AI Order Flow Trading Bot
=================================
Entry point — loads config, bootstraps all layers, and runs the async event loop.

Usage:
    cp .env.example .env        # fill in your API credentials
    pip install -e .
    python main.py              # loads .env
    python main.py --env pairs/xrp.env   # per-pair config (used by launcher.py)
"""

import argparse
import asyncio
import os
import signal
from pathlib import Path

from dotenv import load_dotenv

from src.auth.signer import KrakenAuth
from src.utils.metrics import start_metrics_server
from src.client.rest import KrakenRESTClient
from src.client.websocket import KrakenWebSocket
from src.market_data.orderbook import OrderBook
from src.market_data.ticker import TickerFeed
from src.trading.order_flow import OrderFlowAnalyzer, OrderFlowStrategy
from src.trading.orders import OrderManager
from src.trading.position import PositionTracker
from src.trading.price_action import PriceActionAnalyzer
from src.trading.risk import RiskManager
from src.utils.logger import get_logger


def _config() -> dict:
    return {
        "api_key": os.environ["KRAKEN_API_KEY"],
        "api_secret": os.environ["KRAKEN_API_SECRET"],
        "symbol": os.getenv("TRADING_PAIR", "BTC/USD"),
        "order_size": float(os.getenv("ORDER_SIZE", "0.001")),
        "max_position": float(os.getenv("MAX_POSITION", "0.01")),
        "order_size_usd": float(os.getenv("ORDER_SIZE_USD", "0")),
        "book_depth": int(os.getenv("BOOK_DEPTH", "25")),
        "imbalance_threshold": float(os.getenv("IMBALANCE_THRESHOLD", "0.25")),
        "min_confidence": float(os.getenv("MIN_CONFIDENCE", "0.55")),
        "profit_target_pct": float(os.getenv("PROFIT_TARGET_PCT", "2.5")),  # 2.5% of ORDER_SIZE_USD
        "max_spread_bps": float(os.getenv("MAX_SPREAD_BPS", "15.0")),
        "dead_mans_switch": int(os.getenv("DEAD_MANS_SWITCH_SECONDS", "60")),
        "dry_run": os.getenv("DRY_RUN", "true").lower() == "true",
        "stop_loss_usd": float(os.getenv("STOP_LOSS_USD", "0")),      # overridden by STOP_LOSS_PCT
        "stop_loss_pct": float(os.getenv("STOP_LOSS_PCT", "0.83")),   # 0.83% of ORDER_SIZE_USD
        "risk_reward_ratio": float(os.getenv("RISK_REWARD_RATIO", "3.0")),
        "trail_step_pct": float(os.getenv("TRAIL_STEP_PCT", "0.25")),
        "breakeven_buffer_pct": float(os.getenv("BREAKEVEN_BUFFER_PCT", "0.5")),  # lifts break-even SL above entry to cover taker fee + slippage
        "price_decimals": int(os.getenv("PRICE_DECIMALS", "1")),
        # Price action / trend filter
        "fast_ema": int(os.getenv("FAST_EMA", "20")),
        "slow_ema": int(os.getenv("SLOW_EMA", "60")),
        "spike_threshold": float(os.getenv("SPIKE_THRESHOLD", "0.003")),
        "recovery_pct": float(os.getenv("RECOVERY_PCT", "0.5")),
        "extreme_window": int(os.getenv("EXTREME_WINDOW", "200")),
        "exhaustion_ttl": int(os.getenv("EXHAUSTION_TTL", "60")),
        "retest_proximity": float(os.getenv("RETEST_PROXIMITY", "0.002")),
        "retest_memory_ticks": int(os.getenv("RETEST_MEMORY_TICKS", "400")),
        "retest_ttl": int(os.getenv("RETEST_TTL", "40")),
        # Zone scoring
        "min_zone_score": float(os.getenv("MIN_ZONE_SCORE", "5.0")),
        "basing_ticks_fast": int(os.getenv("BASING_TICKS_FAST", "5")),
        "basing_ticks_slow": int(os.getenv("BASING_TICKS_SLOW", "15")),
        "metrics_port": int(os.getenv("METRICS_PORT", "0")),
        # Stagger DMS calls across pairs so concurrent nonces don't collide on shared API key
        "dms_jitter": int(os.getenv("DMS_INITIAL_JITTER_SECONDS", "0")),
    }


async def run(cfg: dict) -> None:
    log = get_logger("main")
    if cfg["dry_run"]:
        log.info("*** DRY RUN — orders will be validated but NOT submitted ***")

    # Write PID file so the launcher can kill this process cleanly on restart
    _pair_stem = cfg["symbol"].split("/")[0].lower()
    _pid_file = Path("logs") / f"{_pair_stem}.pid"
    _pid_file.parent.mkdir(parents=True, exist_ok=True)
    _pid_file.write_text(str(os.getpid()))

    start_metrics_server()
    if cfg["metrics_port"]:
        log.info("Prometheus metrics on http://localhost:%d/metrics", cfg["metrics_port"])

    # ------------------------------------------------------------------
    # 1. Auth + REST bootstrap
    # ------------------------------------------------------------------
    auth = KrakenAuth(api_key=cfg["api_key"], api_secret=cfg["api_secret"])

    async with KrakenRESTClient(auth) as rest:
        log.info("Fetching WebSocket token via REST...")
        ws_token = await rest.get_websockets_token()
        balance = await rest.get_balance()
        log.info("Balance: %s", balance)
        ticker_snapshot = await rest.get_ticker(cfg["symbol"])

    # ------------------------------------------------------------------
    # 2. Shared state
    # ------------------------------------------------------------------
    orderbook = OrderBook(symbol=cfg["symbol"])
    ticker_feed = TickerFeed()
    position_tracker = PositionTracker()

    # Seed position tracker from live exchange balance so position limits are correct on restart
    _base = cfg["symbol"].split("/")[0].upper()
    _btc_alias = {"BTC": "XBT"}  # Kraken names BTC as XBT internally
    _kraken_base = _btc_alias.get(_base, _base)
    # Try common Kraken balance key formats: XXBT, XXRP, XETH, etc.
    _balance_key = next(
        (k for k in [f"X{_kraken_base}", _kraken_base, f"XX{_kraken_base}"] if k in balance),
        None,
    )
    _base_qty = float(balance.get(_balance_key, 0)) if _balance_key else 0.0

    # Extract current price from ticker (used for position seeding and USD-based sizing)
    _mark = 0.0
    if ticker_snapshot:
        try:
            _ticker_data = next(iter(ticker_snapshot.values()))
            _mark = float(_ticker_data["c"][0])
        except (StopIteration, KeyError, IndexError, TypeError, ValueError):
            pass

    if _base_qty > 0 and _mark > 0:
        position_tracker.seed_position(cfg["symbol"], _base_qty, _mark)
        log.info("Seeded position from balance: %.8f %s @ %.4f", _base_qty, _base, _mark)

    # Dynamic USD-based position sizing: recalculate token qty from live price each restart
    if cfg["order_size_usd"] > 0:
        if _mark > 0:
            _raw_qty = cfg["order_size_usd"] / _mark
            _decimals = 8 if _raw_qty < 0.01 else (4 if _raw_qty < 1 else 2)
            _qty = round(_raw_qty, _decimals)
            cfg["order_size"] = _qty
            cfg["max_position"] = _qty
            log.info(
                "USD sizing: $%.2f @ %.6f → ORDER_SIZE=MAX_POSITION=%.8g tokens",
                cfg["order_size_usd"], _mark, _qty,
            )
        else:
            log.warning(
                "ORDER_SIZE_USD=%.2f set but no live price available — using ORDER_SIZE=%.8g fallback",
                cfg["order_size_usd"], cfg["order_size"],
            )

    # SL and TP are always derived from ORDER_SIZE_USD — never from static USD amounts.
    # This ensures consistent risk regardless of token price.
    _order_usd = cfg["order_size_usd"] if cfg["order_size_usd"] > 0 else cfg["order_size"] * _mark
    if _order_usd <= 0:
        log.error("ORDER_SIZE_USD=0 and no live price — cannot compute SL/TP. Set ORDER_SIZE_USD in pair env.")
        raise SystemExit(1)

    cfg["stop_loss_usd"]   = _order_usd * cfg["stop_loss_pct"]    / 100.0
    cfg["take_profit_usd"] = _order_usd * cfg["profit_target_pct"] / 100.0
    _tp_usd = cfg["take_profit_usd"]

    log.info(
        "Risk: ORDER=$%.2f  SL=%.3f%%=$%.4f  TP=%.1f%%=$%.4f  "
        "trail(25%%=$%.4f  50%%=$%.4f  75%%=$%.4f)",
        _order_usd,
        cfg["stop_loss_pct"],   cfg["stop_loss_usd"],
        cfg["profit_target_pct"], _tp_usd,
        _tp_usd * 0.25, _tp_usd * 0.50, _tp_usd * 0.75,
    )

    analyzer = OrderFlowAnalyzer(
        imbalance_threshold=cfg["imbalance_threshold"],
        min_confidence=cfg["min_confidence"],
    )

    risk_manager = RiskManager(
        stop_loss_usd=cfg["stop_loss_usd"],
        risk_reward_ratio=cfg["risk_reward_ratio"],
        trail_step_pct=cfg["trail_step_pct"],
        take_profit_usd=cfg["take_profit_usd"],
        breakeven_buffer_pct=cfg["breakeven_buffer_pct"],
    )

    price_action = PriceActionAnalyzer(
        fast_period=cfg["fast_ema"],
        slow_period=cfg["slow_ema"],
        spike_threshold=cfg["spike_threshold"],
        recovery_pct=cfg["recovery_pct"],
        extreme_window=cfg["extreme_window"],
        exhaustion_ttl=cfg["exhaustion_ttl"],
        retest_proximity=cfg["retest_proximity"],
        retest_memory_ticks=cfg["retest_memory_ticks"],
        retest_ttl=cfg["retest_ttl"],
        min_zone_score=cfg["min_zone_score"],
        basing_ticks_fast=cfg["basing_ticks_fast"],
        basing_ticks_slow=cfg["basing_ticks_slow"],
    )

    # ------------------------------------------------------------------
    # 3. WebSocket clients
    # ------------------------------------------------------------------
    pub_ws = KrakenWebSocket(authenticated=False)
    auth_ws = KrakenWebSocket(authenticated=True)

    order_manager = OrderManager(ws=auth_ws, token=ws_token)

    async def _refresh_auth_token() -> None:
        """Fetch a fresh WS token and update the stored executions subscription.
        Called automatically before each auth-WS reconnect so the token is never stale.
        Kraken WS tokens expire after ~15 minutes."""
        try:
            async with KrakenRESTClient(auth) as _rest:
                new_token = await _rest.get_websockets_token()
            order_manager.refresh_token(new_token)
            for sub in auth_ws._subscriptions:
                if sub.get("params", {}).get("channel") == "executions":
                    sub["params"]["token"] = new_token
                    sub["params"].pop("snap_orders", None)  # snapshot only needed on first connect
            log.info("WS token refreshed")
        except Exception as exc:
            log.warning("WS token refresh failed: %s", exc)

    auth_ws.on_reconnect = _refresh_auth_token

    strategy = OrderFlowStrategy(
        symbol=cfg["symbol"],
        order_manager=order_manager,
        position_tracker=position_tracker,
        analyzer=analyzer,
        risk_manager=risk_manager,
        order_size=cfg["order_size"],
        max_position=cfg["max_position"],
        max_spread_bps=cfg["max_spread_bps"],
        dead_mans_switch_interval=cfg["dead_mans_switch"],
        price_decimals=cfg["price_decimals"],
        price_action=price_action,
    )
    strategy.attach_orderbook(orderbook)

    # ------------------------------------------------------------------
    # 4. Message routers
    # ------------------------------------------------------------------

    async def on_public(msg: dict) -> None:
        channel = msg.get("channel")
        msg_type = msg.get("type")

        if channel == "book":
            if msg_type == "snapshot":
                data = msg.get("data", [{}])
                orderbook.apply_snapshot(data[0] if data else {})
                log.info(
                    "Book snapshot %s  mid=%.4f  spread=%.4f  imb=%.3f",
                    cfg["symbol"],
                    orderbook.mid_price() or 0,
                    orderbook.spread() or 0,
                    orderbook.imbalance(),
                )
            elif msg_type == "update":
                for upd in msg.get("data", []):
                    orderbook.apply_update(upd)
                    chk = upd.get("checksum")
                    if chk and not orderbook.validate_checksum(chk):
                        pass  # checksum logged at DEBUG; v2 format TBD
                if not cfg["dry_run"]:
                    await strategy.on_book_update()

        elif channel == "trade":
            await strategy.on_trade(msg)
            # update mark price from latest trade
            for t in msg.get("data", []):
                position_tracker.update_mark_price(cfg["symbol"], float(t.get("price", 0)))

        elif channel == "ticker":
            for t in msg.get("data", []):
                ticker_feed.update(t)

        elif channel == "heartbeat":
            pass  # connection alive

        elif channel == "status":
            log.info("System status: %s", msg.get("data"))

    async def on_auth(msg: dict) -> None:
        channel = msg.get("channel")
        method = msg.get("method")

        if channel == "executions":
            await strategy.on_execution(msg)

        elif method in ("add_order", "amend_order", "cancel_order", "cancel_all", "batch_add"):
            if msg.get("success"):
                result = msg.get("result", {})
                log.info(
                    "Order ACK  method=%s  order_id=%s  cl_ord_id=%s",
                    method,
                    result.get("order_id", "—"),
                    result.get("cl_ord_id", "—"),
                )
            else:
                log.error("Order NACK  method=%s  error=%s", method, msg.get("error"))
                if method == "add_order":
                    await strategy.on_order_nack(msg.get("error", ""))

        elif channel == "heartbeat":
            pass

    pub_ws.on_message = on_public
    auth_ws.on_message = on_auth

    # ------------------------------------------------------------------
    # 5. Subscribe after connections are live
    # ------------------------------------------------------------------

    async def subscribe_public() -> None:
        await pub_ws.wait_connected()
        await pub_ws.subscribe({
            "channel": "book",
            "symbol": [cfg["symbol"]],
            "depth": cfg["book_depth"],
            "snapshot": True,
        })
        await pub_ws.subscribe({"channel": "trade", "symbol": [cfg["symbol"]]})
        await pub_ws.subscribe({"channel": "ticker", "symbol": [cfg["symbol"]]})
        log.info("Public subscriptions sent for %s", cfg["symbol"])

    async def subscribe_auth() -> None:
        await auth_ws.wait_connected()
        await auth_ws.subscribe({
            "channel": "executions",
            "token": ws_token,
            "snap_orders": True,
            "snap_trades": False,
            "order_status": True,
        })
        log.info("Authenticated executions subscription sent")

    # ------------------------------------------------------------------
    # 6. Dead-man's switch refresh loop (REST)
    # ------------------------------------------------------------------

    async def dead_mans_switch_loop() -> None:
        if cfg["dry_run"]:
            return
        # Stagger first call so pairs don't all hit REST at the same microsecond
        # (shared API key → nonces must be strictly increasing; concurrent calls collide)
        if cfg["dms_jitter"] > 0:
            log.debug("DMS jitter: sleeping %ds before first refresh", cfg["dms_jitter"])
            await asyncio.sleep(cfg["dms_jitter"])
        async with KrakenRESTClient(auth) as rest:
            while True:
                try:
                    await rest.cancel_all_orders_after(cfg["dead_mans_switch"] * 2)
                    log.debug("Dead-man's switch refreshed (%ds)", cfg["dead_mans_switch"] * 2)
                except Exception as exc:
                    log.warning("Dead-man's switch refresh failed: %s", exc)
                await asyncio.sleep(cfg["dead_mans_switch"])

    # ------------------------------------------------------------------
    # 6b. Heartbeat logger — keeps the log stream alive during idle periods
    # ------------------------------------------------------------------

    async def heartbeat_loop() -> None:
        while True:
            await asyncio.sleep(60)
            ob = orderbook
            mid = ob.mid_price()
            pos = position_tracker.get_position(cfg["symbol"])
            log.info(
                "HEARTBEAT | mid=%.6f  pos=%.6f  usd=%.2f",
                mid or 0.0,
                pos.qty,
                pos.qty * (mid or 0.0),
            )

    # ------------------------------------------------------------------
    # 7. Graceful shutdown
    # ------------------------------------------------------------------

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _handle_signal() -> None:
        log.info("Shutdown signal received — cancelling all orders and exiting")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    async def shutdown_guard() -> None:
        await shutdown_event.wait()
        if not cfg["dry_run"]:
            async with KrakenRESTClient(auth) as rest:
                try:
                    await rest.cancel_all_orders()
                    log.info("All orders cancelled on shutdown")
                except Exception as exc:
                    log.error("Failed to cancel orders on shutdown: %s", exc)
        await pub_ws.disconnect()
        await auth_ws.disconnect()
        # Remove PID file so the launcher knows this process is fully gone
        try:
            _pid_file.unlink(missing_ok=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 8. Run everything
    # ------------------------------------------------------------------
    log.info(
        "Starting Kraken Order Flow Bot | symbol=%s size=%s max_pos=%s dry_run=%s",
        cfg["symbol"], cfg["order_size"], cfg["max_position"], cfg["dry_run"],
    )

    await asyncio.gather(
        pub_ws.connect(),
        auth_ws.connect(),
        subscribe_public(),
        subscribe_auth(),
        dead_mans_switch_loop(),
        heartbeat_loop(),
        shutdown_guard(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Kraken order-flow trading bot")
    parser.add_argument("--env", default=".env", help="Path to .env file (default: .env)")
    args = parser.parse_args()

    load_dotenv(args.env, override=True)

    log = get_logger("main")

    try:
        cfg = _config()
    except KeyError as exc:
        log.error("Missing required env var: %s  — check your .env file", exc)
        raise SystemExit(1)

    asyncio.run(run(cfg))


if __name__ == "__main__":
    main()
