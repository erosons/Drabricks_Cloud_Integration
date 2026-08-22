"""Order-flow engine — kraken two-layer signal engine + futures gates (§7).

Pipeline per book update:
  F1 session → F2 news → F3 contract staleness → F4 lifecycle
  → Gate 0 pre-checks (spread ticks, cooldown, NACK pause)
  → Layer 1 order flow (0.6·imbalance + 0.4·trade delta, confidence gate)
  → Layer 2 price action (EMA trend / V-exhaustion / re-test truth table)
  → symmetric entry: BUY & flat → long, SELL & flat → short (futures!)
  → OSO bracket at best bid/ask on the ACTIVE month, tick-quantized

Exits: the quadrant trail (risk.py) modifies the server-side stop; TP or a
local SL breach flattens. Executors: DryRunExecutor logs and simulates
nothing; TradovateExecutor (live/demo) goes through the gateway.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from src.market_data.orderbook import OrderBook
from src.trading.position import PositionTracker
from src.trading.price_action import PriceActionAnalyzer
from src.trading.risk import RiskManager, round_to_tick
from src.trading.signals import Signal
from src.utils.logger import get_logger
from src.utils.metrics import BotMetrics


@dataclass
class TradeEvent:
    price: float
    qty: float
    side: str
    timestamp: str


@dataclass
class FlowSignal:
    signal: Signal
    confidence: float
    imbalance: float
    trade_flow_delta: float
    reasoning: str


class OrderFlowAnalyzer:
    """Layer 1 — unchanged from kraken: book imbalance + trade-flow delta."""

    def __init__(self, imbalance_threshold: float = 0.25,
                 trade_window: int = 50, book_depth: int = 10,
                 min_confidence: float = 0.55):
        self.imbalance_threshold = imbalance_threshold
        self.book_depth = book_depth
        self.min_confidence = min_confidence
        self._trades: deque[TradeEvent] = deque(maxlen=trade_window)

    def add_trade(self, price: float, qty: float, side: str, timestamp: str) -> None:
        self._trades.append(TradeEvent(price, qty, side, timestamp))

    def trade_flow_delta(self) -> float:
        if not self._trades:
            return 0.0
        buy_vol = sum(t.qty for t in self._trades if t.side == "buy")
        sell_vol = sum(t.qty for t in self._trades if t.side == "sell")
        total = buy_vol + sell_vol
        return (buy_vol - sell_vol) / total if total else 0.0

    def analyze(self, book: OrderBook) -> FlowSignal:
        imbalance = book.imbalance(self.book_depth)
        tfd = self.trade_flow_delta()
        score = 0.6 * imbalance + 0.4 * tfd
        confidence = min(abs(score) / max(self.imbalance_threshold, 1e-6), 1.0)
        if score > self.imbalance_threshold:
            signal = Signal.BUY
        elif score < -self.imbalance_threshold:
            signal = Signal.SELL
        else:
            signal = Signal.NEUTRAL
        return FlowSignal(signal, confidence, imbalance, tfd,
                          f"score={score:.3f} imb={imbalance:.3f} tfd={tfd:.3f}")


class Executor(Protocol):
    async def enter(self, symbol: str, side: str, qty: int,
                    limit_price: float, bracket_stop: float) -> bool: ...
    async def modify_stop(self, symbol: str, new_stop: float) -> None: ...
    async def flatten(self, symbol: str, reason: str) -> None: ...
    async def cancel_working(self, symbol: str, reason: str) -> None: ...


class DryRunExecutor:
    """dry_run: true — announces intent, sends NOTHING anywhere (§2)."""

    def __init__(self, product: str):
        self.log = get_logger(f"dryrun.{product}")
        self.entries: list[dict] = []

    async def enter(self, symbol, side, qty, limit_price, bracket_stop) -> bool:
        self.entries.append({"symbol": symbol, "side": side, "qty": qty,
                             "limit": limit_price, "stop": bracket_stop})
        self.log.info("DRY-RUN would ENTER %s %s x%d limit=%.2f bracket_stop=%.2f",
                      side.upper(), symbol, qty, limit_price, bracket_stop)
        return True

    async def modify_stop(self, symbol, new_stop) -> None:
        self.log.info("DRY-RUN would MODIFY STOP %s → %.2f", symbol, new_stop)

    async def flatten(self, symbol, reason) -> None:
        self.log.info("DRY-RUN would FLATTEN %s (%s)", symbol, reason)

    async def cancel_working(self, symbol, reason) -> None:
        self.log.info("DRY-RUN would CANCEL working orders %s (%s)", symbol, reason)


class FuturesOrderFlowStrategy:
    ORDER_COOLDOWN = 10.0

    def __init__(self, *, product, contract_symbol: str,
                 analyzer: OrderFlowAnalyzer,
                 price_action: PriceActionAnalyzer | None,
                 risk_manager: RiskManager,
                 position_tracker: PositionTracker,
                 executor: Executor,
                 session_manager, news_guard,
                 lifecycle_ok=lambda: True,
                 contract_fresh=lambda: True,
                 max_spread_ticks: float = 2.0,
                 now_fn=lambda: datetime.now(timezone.utc)):
        self.product = product
        self.contract_symbol = contract_symbol
        self.analyzer = analyzer
        self.price_action = price_action
        self.risk = risk_manager
        self.positions = position_tracker
        self.executor = executor
        self.session = session_manager
        self.news = news_guard
        self.lifecycle_ok = lifecycle_ok
        self.contract_fresh = contract_fresh
        self.max_spread_ticks = max_spread_ticks
        self.now_fn = now_fn

        self.book: OrderBook | None = None
        self.metrics = BotMetrics(product.symbol)
        self.log = get_logger(f"engine.{product.symbol}")
        self._last_order_time = 0.0
        self._nack_pause_until = 0.0
        self._round_trip_pnl_base = 0.0   # realized P&L when the trip opened
        self._flattened_this_session = False
        self._prev_tick_at: datetime | None = None
        self.skips: dict[str, int] = {}

    def attach_orderbook(self, book: OrderBook) -> None:
        self.book = book

    def _skip(self, gate: str) -> None:
        self.skips[gate] = self.skips.get(gate, 0) + 1

    # ------------------------------------------------------------------

    async def on_book_update(self) -> None:
        book = self.book
        if book is None or not book.synced:
            return
        now = self.now_fn()
        mid = book.mid_price()
        if mid is None:
            return

        # feed analytics + risk on EVERY tick, even while gated
        if self.price_action:
            self.price_action.on_price_tick(mid)
        self.positions.update_mark_price(self.contract_symbol, mid)
        await self._manage_open_position(mid, now)

        # ---- futures gates (§7) ----
        if not self.session.is_entry_allowed(now):
            if self.session.should_flatten(now):
                await self._session_flatten()
            return self._skip("F1_session")
        self._flattened_this_session = False

        blackout = self.news.entering_blackout(self._prev_tick_at or now, now)
        self._prev_tick_at = now
        if blackout is not None:
            await self.executor.cancel_working(
                self.contract_symbol, f"blackout: {blackout.title}")
        if self.news.active_blackout(now) is not None:
            return self._skip("F2_news")
        if not self.contract_fresh():
            return self._skip("F3_contract_stale")
        if not self.lifecycle_ok():
            return self._skip("F4_lifecycle")

        # ---- gate 0 pre-checks ----
        wall = time.monotonic()
        if wall < self._nack_pause_until:
            return self._skip("G0_nack_pause")
        if wall - self._last_order_time < self.ORDER_COOLDOWN:
            return self._skip("G0_cooldown")
        spread = book.spread_ticks()
        if spread is None or spread > self.max_spread_ticks:
            return self._skip("G0_spread")

        # ---- layer 1: order flow ----
        flow = self.analyzer.analyze(book)
        if flow.confidence < self.analyzer.min_confidence:
            return self._skip("L1_confidence")

        # ---- layer 2: price action gate (kraken truth table) ----
        effective = self._gate_signal(flow.signal)
        self.metrics.update_signal(effective.value)
        if effective == Signal.NEUTRAL:
            return self._skip("L2_price_action")

        # ---- symmetric futures entry: only when FLAT ----
        pos = self.positions.get_position(self.contract_symbol)
        if pos.qty != 0 or self.risk.has_position(self.contract_symbol):
            return self._skip("in_position")

        await self._enter(effective, book)
        self.log.debug("flow=%s effective=%s conf=%.2f | %s",
                       flow.signal, effective, flow.confidence, flow.reasoning)

    async def on_trade(self, price: float, qty: float, side: str,
                       timestamp: str = "") -> None:
        self.analyzer.add_trade(price, qty, side, timestamp)
        await self._manage_open_position(price, self.now_fn())

    async def on_fill(self, side: str, qty: int, price: float,
                      fee: float = 0.0) -> None:
        """Execution event from the broker (or the incubator's paper fills)."""
        was_flat = self.positions.get_position(self.contract_symbol).qty == 0
        self.positions.on_fill(self.contract_symbol, side, qty, price, fee)
        pos = self.positions.get_position(self.contract_symbol)
        if pos.qty != 0 and not self.risk.has_position(self.contract_symbol):
            self.risk.on_entry(self.contract_symbol, pos.avg_price,
                               abs(pos.qty), "buy" if pos.qty > 0 else "sell")
            self.metrics.inc_orders_filled()
            if was_flat:
                self._round_trip_pnl_base = pos.realized_pnl
        elif pos.qty == 0:
            self.risk.on_exit(self.contract_symbol)
            # round trip closed — win/loss by realized P&L delta, fees included
            self.metrics.inc_trade_closed(
                pos.realized_pnl - self._round_trip_pnl_base)
            self._round_trip_pnl_base = pos.realized_pnl

    async def on_order_nack(self, error: str = "") -> None:
        self._last_order_time = time.monotonic()
        self._nack_pause_until = time.monotonic() + 60.0
        self.metrics.inc_orders_rejected()
        self.log.warning("Order NACK (%s) — 60s pause", error or "unknown")

    # ------------------------------------------------------------------

    def _gate_signal(self, flow: Signal) -> Signal:
        """Kraken truth table: exhaustion overrides trend but must agree with
        flow; otherwise trend and flow must agree."""
        if self.price_action is None:
            return flow
        pa = self.price_action.analyze()
        if pa.exhaustion != Signal.NEUTRAL:
            return flow if pa.exhaustion == flow else Signal.NEUTRAL
        if pa.trend == flow and flow != Signal.NEUTRAL:
            return flow
        return Signal.NEUTRAL

    async def _enter(self, signal: Signal, book: OrderBook) -> None:
        side = "buy" if signal == Signal.BUY else "sell"
        level = book.best_bid() if side == "buy" else book.best_ask()
        if level is None:
            return
        limit_price = round_to_tick(level[0], self.product.tick_size)
        sign = 1 if side == "buy" else -1
        bracket_stop = round_to_tick(
            limit_price - sign * self.risk.geometry.stop_ticks * self.product.tick_size,
            self.product.tick_size)
        qty = self.product.risk.max_contracts

        self._last_order_time = time.monotonic()
        sent = await self.executor.enter(self.contract_symbol, side, qty,
                                         limit_price, bracket_stop)
        if sent:
            self.metrics.inc_orders_placed()

    async def _manage_open_position(self, price: float, now) -> None:
        if not self.risk.has_position(self.contract_symbol):
            return
        update = self.risk.on_price_update(self.contract_symbol, price)
        if update.new_stop is not None:
            await self.executor.modify_stop(self.contract_symbol, update.new_stop)
        if update.reason != "none":
            await self.executor.flatten(self.contract_symbol, update.reason)
            self.risk.on_exit(self.contract_symbol)
            if update.reason == "sl":
                self.metrics.inc_sl_hit()
            else:
                self.metrics.inc_tp_hit()

    async def _session_flatten(self) -> None:
        if self._flattened_this_session:
            return
        self._flattened_this_session = True
        await self.executor.cancel_working(self.contract_symbol, "session close")
        pos = self.positions.get_position(self.contract_symbol)
        if pos.qty != 0 or self.risk.has_position(self.contract_symbol):
            await self.executor.flatten(self.contract_symbol, "session close 15:55 ET")
            self.risk.on_exit(self.contract_symbol)
