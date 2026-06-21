import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo

from ..market_data.orderbook import OrderBook
from ..trading.orders import OrderManager, OrderSide, TimeInForce
from ..trading.position import PositionTracker
from ..trading.risk import RiskManager
from ..trading.signals import Signal
from ..trading.trade_slots import acquire_slot, release_slot
from ..utils.logger import get_logger
from ..utils.metrics import BotMetrics

if TYPE_CHECKING:
    from ..trading.price_action import PriceActionAnalyzer, PriceActionSignal

_ET = ZoneInfo("America/New_York")


def _in_trading_hours() -> bool:
    """True if current ET time is 07:00–14:59 Sunday–Friday (no Saturday trading)."""
    now = datetime.now(_ET)
    if now.weekday() == 5:          # Saturday = 5
        return False
    return 7 <= now.hour < 15       # 7:00 AM to 2:59:59 PM ET


@dataclass
class TradeEvent:
    price: float
    qty: float
    side: str       # "buy" or "sell"
    timestamp: str


@dataclass
class FlowSignal:
    signal: Signal
    confidence: float       # 0.0–1.0
    imbalance: float        # order book imbalance
    trade_flow_delta: float # normalized buy - sell volume
    reasoning: str


class OrderFlowAnalyzer:
    """
    Combines two signals to determine directional bias:

    1. Order Book Imbalance  — bid_vol vs ask_vol in top N levels.
       Positive → more buy-side interest.

    2. Trade Flow Delta — recent taker buy volume vs sell volume.
       Positive → buyers are more aggressive.

    Combined score = 0.6 * imbalance + 0.4 * trade_flow_delta
    """

    def __init__(
        self,
        imbalance_threshold: float = 0.25,
        trade_window: int = 50,
        book_levels: int = 10,
        min_confidence: float = 0.55,
    ) -> None:
        self.imbalance_threshold = imbalance_threshold
        self.book_levels = book_levels
        self.min_confidence = min_confidence
        self._trades: deque[TradeEvent] = deque(maxlen=trade_window)

    def add_trade(self, price: float, qty: float, side: str, timestamp: str) -> None:
        self._trades.append(TradeEvent(price=price, qty=qty, side=side, timestamp=timestamp))

    def trade_flow_delta(self) -> float:
        if not self._trades:
            return 0.0
        buy_vol = sum(t.qty for t in self._trades if t.side == "buy")
        sell_vol = sum(t.qty for t in self._trades if t.side == "sell")
        total = buy_vol + sell_vol
        return (buy_vol - sell_vol) / total if total else 0.0

    def analyze(self, orderbook: OrderBook) -> FlowSignal:
        imbalance = orderbook.imbalance(self.book_levels)
        tfd = self.trade_flow_delta()
        score = 0.6 * imbalance + 0.4 * tfd
        confidence = min(abs(score) / max(self.imbalance_threshold, 1e-6), 1.0)

        if score > self.imbalance_threshold:
            signal = Signal.BUY
        elif score < -self.imbalance_threshold:
            signal = Signal.SELL
        else:
            signal = Signal.NEUTRAL

        return FlowSignal(
            signal=signal,
            confidence=confidence,
            imbalance=imbalance,
            trade_flow_delta=tfd,
            reasoning=f"score={score:.3f} imb={imbalance:.3f} tfd={tfd:.3f}",
        )


class OrderFlowStrategy:
    """
    Passive order-flow strategy for spot trading.

    Entry logic:
    - BUY  signal + no position → post limit bid just inside best bid
    - SELL signal + open position → post limit ask just inside best ask
    - Signal too weak or spread too wide → do nothing

    Risk controls:
    - max_position: maximum base asset held
    - max_spread_bps: skip if spread exceeds this
    - dead_mans_switch_interval: REST heartbeat to cancel all if bot dies
    """

    def __init__(
        self,
        symbol: str,
        order_manager: OrderManager,
        position_tracker: PositionTracker,
        analyzer: OrderFlowAnalyzer,
        risk_manager: RiskManager,
        order_size: float,
        max_position: float,
        max_spread_bps: float = 15.0,
        dead_mans_switch_interval: int = 60,
        price_decimals: int = 1,
        price_action: Optional["PriceActionAnalyzer"] = None,
    ) -> None:
        self.symbol = symbol
        self.order_manager = order_manager
        self.position_tracker = position_tracker
        self.analyzer = analyzer
        self.risk_manager = risk_manager
        self.order_size = order_size
        self.max_position = max_position
        self.max_spread_bps = max_spread_bps
        self.dead_mans_switch_interval = dead_mans_switch_interval
        self.price_decimals = price_decimals
        self.price_action = price_action

        self._orderbook: Optional[OrderBook] = None
        self._active_cl_id: Optional[str] = None   # current working order
        self._last_signal: Signal = Signal.NEUTRAL
        self._consecutive_nacks: int = 0
        self._nack_pause_until: float = 0.0
        self._last_order_time: float = 0.0
        self._order_lock: asyncio.Lock = asyncio.Lock()
        self._in_trade: bool = False  # True from first buy fill until position fully exits
        self.log = get_logger(__name__)
        self.metrics = BotMetrics(pair=symbol)

    # seconds to wait after any order event before posting again
    ORDER_COOLDOWN = 10.0

    def attach_orderbook(self, orderbook: OrderBook) -> None:
        self._orderbook = orderbook

    # ------------------------------------------------------------------
    # Event handlers  (called by the message router in main.py)
    # ------------------------------------------------------------------

    async def on_book_update(self) -> None:
        ob = self._orderbook
        if ob is None:
            return

        # Feed mid-price into price action analyzer on every tick
        mid = ob.mid_price()
        if mid and self.price_action:
            self.price_action.on_price_tick(mid)
            pa = self.price_action.analyze()
            self.metrics.update_emas(pa.fast_ema, pa.slow_ema, mid)
        elif mid:
            self.metrics.update_emas(0.0, 0.0, mid)

        # Keep position metrics current on every book tick (survives bot restarts)
        if mid:
            self.position_tracker.update_mark_price(self.symbol, mid)
            rpnl, upnl = self.position_tracker.get_total_pnl()
            self.metrics.update_pnl(rpnl, upnl)
            pos  = self.position_tracker.get_position(self.symbol)
            risk = self.risk_manager.get_risk(self.symbol)

            if pos.qty == 0 and risk is not None:
                # Position was closed externally (UI/manual) — release slot and clear risk
                self.log.info("External close detected for %s — releasing slot", self.symbol)
                self.risk_manager.on_exit(self.symbol)
                release_slot(self.symbol)
                self._in_trade = False
                risk = None

            elif pos.qty > 0 and risk is None and pos.avg_price > 0:
                # Ignore dust balances — only re-seed if position is worth > $1
                if pos.qty * mid > 1.0:
                    if acquire_slot(self.symbol):
                        self.risk_manager.on_entry(self.symbol, pos.avg_price, pos.qty, "buy")
                        risk = self.risk_manager.get_risk(self.symbol)
                        self.log.info("Re-seeded risk for existing position %s", self.symbol)

            sl = risk.sl_price if risk else 0.0
            tp = risk.tp_price if risk else 0.0
            self.metrics.update_position(pos.qty, sl, tp)

        now = time.time()
        if now < self._nack_pause_until:
            return
        if now - self._last_order_time < self.ORDER_COOLDOWN:
            return

        spread_bps = ob.spread_bps()
        if spread_bps is None or spread_bps > self.max_spread_bps:
            return

        flow = self.analyzer.analyze(ob)
        if flow.confidence < self.analyzer.min_confidence:
            return

        # Apply price action gate — combines trend filter + exhaustion override
        effective = self._gate_signal(flow.signal)

        # Update signal metric regardless of gate outcome
        pa_state = self.price_action.analyze() if self.price_action else None
        self.metrics.update_signal(
            effective.value,
            exhaustion_active=(pa_state is not None and pa_state.exhaustion != Signal.NEUTRAL),
        )

        if effective == Signal.NEUTRAL:
            return

        # Lock prevents concurrent cancel+repost cycles from overlapping
        if self._order_lock.locked():
            return
        async with self._order_lock:
            # cancel stale working order when effective signal flips
            if effective != self._last_signal and self._active_cl_id:
                open_orders = self.order_manager.get_open_orders()
                for o in open_orders:
                    if o.cl_ord_id == self._active_cl_id and o.order_id:
                        await self.order_manager.cancel_order(o.order_id)
                self._active_cl_id = None

            self._last_signal = effective
            pos = self.position_tracker.get_position(self.symbol)

            if self._active_cl_id is not None:
                return

            if effective == Signal.BUY and pos.qty == 0 and not self._in_trade:
                if not _in_trading_hours():
                    self.log.debug("Outside trading hours (7am–3pm ET, Sun–Fri) — skipping entry")
                    return
                if not acquire_slot(self.symbol):
                    self.log.debug("Slot cap reached — skipping entry for %s", self.symbol)
                    return
                await self._post_bid(ob)
            elif effective == Signal.SELL and pos.qty > 0 and self._in_trade:
                await self._post_ask(ob)

        self.log.debug(
            "flow=%s effective=%s conf=%.2f | %s",
            flow.signal, effective, flow.confidence, flow.reasoning,
        )

    async def on_trade(self, msg: dict) -> None:
        """Process public trade stream to feed the analyzer and check SL/TP."""
        for trade in msg.get("data", []):
            price = float(trade.get("price", 0))
            self.analyzer.add_trade(
                price=price,
                qty=float(trade.get("qty", 0)),
                side=trade.get("side", "buy"),
                timestamp=trade.get("timestamp", ""),
            )
            if price and self.risk_manager.has_position(self.symbol):
                reason, exit_price = self.risk_manager.on_price_update(self.symbol, price)
                if reason != "none":
                    await self._exit_position(reason, exit_price)

    async def on_order_nack(self, error: str = "") -> None:
        """Clear active order tracking when an order is rejected by the exchange."""
        self._active_cl_id = None
        self._last_order_time = time.time()   # enforce cooldown before retrying
        if "Insufficient funds" in error:
            self._consecutive_nacks += 1
            if self._consecutive_nacks >= 3:
                pause_secs = 60
                self._nack_pause_until = time.time() + pause_secs
                self.log.warning(
                    "Pausing order submission %ds — %d consecutive insufficient-funds NACKs",
                    pause_secs, self._consecutive_nacks,
                )
        else:
            self._consecutive_nacks = 0

    async def on_execution(self, msg: dict) -> None:
        """Reconcile order state and update positions on fills."""
        self.order_manager.on_execution(msg)
        for event in msg.get("data", []):
            if event.get("exec_type") == "trade":
                symbol = event.get("symbol", self.symbol)
                # Kraken executions channel delivers ALL account fills —
                # ignore fills that belong to other pairs running on the same key
                if symbol != self.symbol:
                    continue
                side = event.get("side", "buy")
                qty = float(event.get("last_qty", 0))
                price = float(event.get("last_price", 0))
                fee = float(event.get("fee", 0))   # actual fee, not trade cost

                self.position_tracker.on_fill(
                    symbol=symbol, side=side, qty=qty, price=price, fee=fee,
                )
                rpnl, upnl = self.position_tracker.get_total_pnl()
                self.log.info("PnL  rPnL=%.4f  uPnL=%.4f", rpnl, upnl)
                self.metrics.update_pnl(rpnl, upnl)

                # clear active order only when OUR order is fully filled
                remaining = float(event.get("remaining_qty", 0))
                event_cl_id = event.get("cl_ord_id", "")
                if remaining == 0 and event_cl_id and event_cl_id == self._active_cl_id:
                    self._active_cl_id = None
                    self._consecutive_nacks = 0
                    self.metrics.inc_orders_filled()

                # register entry with risk manager after a new fill opens a position
                # use max_position as qty so SL/TP are calculated for the full
                # planned exposure, not just the first partial fill
                pos = self.position_tracker.get_position(symbol)
                if qty > 0 and pos.qty > 0 and not self.risk_manager.has_position(symbol):
                    self._in_trade = True   # block all new entries until this position exits
                    self.risk_manager.on_entry(
                        symbol=symbol,
                        entry_price=pos.avg_price,
                        qty=self.max_position,
                        side=side,
                    )
                elif qty > 0 and side == "buy" and self.risk_manager.has_position(symbol):
                    # Additional BUY fill added to an existing position — keep entry_price
                    # in sync with the true weighted average so that milestone 1 ("break-even")
                    # is break-even relative to ALL fills, not just the first one.
                    # Stop updating once milestone 1 fires (trail lock-in must never retreat).
                    _risk = self.risk_manager.get_risk(symbol)
                    if _risk and _risk.milestones_hit == 0:
                        sl_per_unit = _risk.stop_loss_usd / _risk.qty
                        tp_per_unit = _risk.take_profit_usd / _risk.qty
                        _risk.entry_price = pos.avg_price
                        _risk.sl_price    = pos.avg_price - sl_per_unit
                        _risk.tp_price    = pos.avg_price + tp_per_unit
                        self.log.debug(
                            "Entry price updated  %s  avg=%.5f  SL=%.5f  TP=%.5f",
                            symbol, pos.avg_price, _risk.sl_price, _risk.tp_price,
                        )

                # update position + SL/TP metrics
                _risk = self.risk_manager.get_risk(symbol)
                self.metrics.update_position(
                    qty=pos.qty,
                    sl=_risk.sl_price if _risk else 0.0,
                    tp=_risk.tp_price if _risk else 0.0,
                )

    # ------------------------------------------------------------------
    # Price action gate
    # ------------------------------------------------------------------

    def _gate_signal(self, flow: Signal) -> Signal:
        """
        Combine the raw order-flow signal with price action context.

        Rules:
          exhaustion=V-BOTTOM + flow=BUY  → BUY   (reversal entry, trend override)
          exhaustion=V-TOP    + flow=SELL → SELL  (reversal entry, trend override)
          trend=UP   + flow=BUY           → BUY   (trend continuation)
          trend=DOWN + flow=SELL          → SELL  (trend continuation)
          everything else                 → NEUTRAL (skip — conflict or low info)
        """
        if self.price_action is None:
            return flow  # no PA analyzer wired — pass through unchanged

        pa = self.price_action.analyze()

        if pa.exhaustion != Signal.NEUTRAL:
            # V-bottom or V-top detected — override EMA trend
            # but still require flow to agree (confirms buyers/sellers are there)
            if pa.exhaustion == flow:
                self.log.info(
                    "PA REVERSAL %s  zone_score=%.1f/8 | %s",
                    flow.value.upper(), pa.zone_score, pa.reasoning,
                )
                return flow
            # Exhaustion signal but flow disagrees — bounce may have failed, skip
            return Signal.NEUTRAL

        # No exhaustion — require trend and flow to agree
        if pa.trend == flow and flow != Signal.NEUTRAL:
            return flow

        # Trend and flow conflict, or not enough data yet
        return Signal.NEUTRAL

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _post_bid(self, ob: OrderBook) -> None:
        bb = ob.best_bid()
        if not bb:
            return
        # join the best bid — guaranteed maker, no post_only rejection
        price = round(bb[0], self.price_decimals)
        available = self.max_position - self.position_tracker.get_position(self.symbol).qty
        qty = min(self.order_size, available)
        if qty <= 0:
            return
        self._active_cl_id = "__pending__"
        self._last_order_time = time.time()
        order = await self.order_manager.place_limit_order(
            symbol=self.symbol,
            side=OrderSide.BUY,
            qty=qty,
            price=price,
        )
        if order is None:
            self._active_cl_id = None   # send failed — allow retry on next tick
            return
        self._active_cl_id = order.cl_ord_id
        self.metrics.inc_orders_placed()

    async def _post_ask(self, ob: OrderBook) -> None:
        ba = ob.best_ask()
        if not ba:
            return
        # join the best ask — guaranteed maker, no post_only rejection
        price = round(ba[0], self.price_decimals)
        pos_qty = self.position_tracker.get_position(self.symbol).qty
        qty = min(self.order_size, pos_qty)
        if qty <= 0:
            return
        self._active_cl_id = "__pending__"
        self._last_order_time = time.time()
        order = await self.order_manager.place_limit_order(
            symbol=self.symbol,
            side=OrderSide.SELL,
            qty=qty,
            price=price,
        )
        if order is None:
            self._active_cl_id = None   # send failed — allow retry on next tick
            return
        self._active_cl_id = order.cl_ord_id
        self.metrics.inc_orders_placed()

    async def _exit_position(self, reason: str, trigger_price: float) -> None:
        """Market-close the full position on SL or TP hit."""
        pos = self.position_tracker.get_position(self.symbol)
        if pos.qty <= 0:
            self.risk_manager.on_exit(self.symbol)
            return

        risk = self.risk_manager.get_risk(self.symbol)
        exit_side = OrderSide.SELL if (risk and risk.side == "buy") else OrderSide.BUY

        self.log.info(
            "Exiting position  reason=%s  trigger=%.4f  qty=%.8f  side=%s",
            reason, trigger_price, pos.qty, exit_side,
        )

        # cancel any pending working order first
        if self._active_cl_id:
            open_orders = self.order_manager.get_open_orders()
            for o in open_orders:
                if o.cl_ord_id == self._active_cl_id and o.order_id:
                    await self.order_manager.cancel_order(o.order_id)
            self._active_cl_id = None

        exit_order = await self.order_manager.place_market_order(
            symbol=self.symbol,
            side=exit_side,
            qty=pos.qty,
        )
        if exit_order is None:
            self.log.warning("Exit market order not sent (socket down) — will retry on next tick")
            return
        self.risk_manager.on_exit(self.symbol)
        release_slot(self.symbol)
        self._in_trade = False   # position closed — allow next entry
        if reason == "stop_loss":
            self.metrics.inc_sl_hit()
        elif reason == "take_profit":
            self.metrics.inc_tp_hit()
        self.metrics.update_position(qty=0.0, sl=0.0, tp=0.0)
