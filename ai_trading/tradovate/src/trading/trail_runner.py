"""Live runner for momentum_dollar_trail — DEMO ONLY (plan/plan.md).

Drives the frozen pure-20-point-trail config against the live Databento
feed and the Tradovate DEMO order path. This is NOT the strategy factory
promoting a strategy: momentum_dollar_trail has not passed gates G2-G4
(holdout −$4.93/trade), and this runner refuses to start when
live_trading: true. Its purpose is the Monday market rehearsal: prove
the full order plumbing under a strategy that actually trades daily, and
measure live fill quality against the sim's assumptions.

Logic (mirrors card_strategies.MomentumDollarTrail exactly; parity is
unit-tested):
  * 1m bars aggregated from live trades
  * entry: two consecutive same-direction 1m closes summing ≥ 2 ticks →
    marketable limit (2 ticks through the last close) with the OSO
    bracket stop at close ∓ trail distance
  * trail: stop ratchets to (extreme since entry ∓ trail) once per bar
    close, via modify_stop — never loosens
  * no target; exit by trail or the 15:55 ET session flatten
  * one position (LiveExecutor's one-bracket guard), re-entry allowed
    whenever the signal reappears
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.utils.logger import get_logger

log = get_logger("trail_runner")


@dataclass
class Bar:
    minute: int          # epoch minutes (ts // 60e9)
    open: float
    high: float
    low: float
    close: float


class BarAggregator:
    """Live trades → completed 1m bars. Returns the CLOSED bar (or None)
    each time a trade arrives in a newer minute."""

    def __init__(self) -> None:
        self.cur: Bar | None = None

    def on_trade(self, ts_ns: int, price: float) -> Bar | None:
        minute = int(ts_ns // 60_000_000_000)
        closed = None
        if self.cur is None or minute > self.cur.minute:
            closed = self.cur
            self.cur = Bar(minute, price, price, price, price)
        else:
            self.cur.high = max(self.cur.high, price)
            self.cur.low = min(self.cur.low, price)
            self.cur.close = price
        return closed


class TrailRunner:
    """Bar-close decision loop; satisfies the engine surface that
    main._attach_order_path expects (product, contract_symbol, on_fill,
    on_order_nack, executor)."""

    def __init__(self, product, contract_symbol: str, params: dict,
                 session_manager, now_fn=lambda: datetime.now(timezone.utc)):
        self.product = product
        self.contract_symbol = contract_symbol
        self.session = session_manager
        self.now_fn = now_fn
        self.tick = product.tick_size
        usd_per_point = product.tick_value / product.tick_size
        self.trail = float(params["trail_dollars"])
        self.init_dist = min(self.trail,
                             float(params["max_loss_usd"]) / usd_per_point)
        self.trigger = params["move_trigger_ticks"] * self.tick

        self.bars = BarAggregator()
        self.prev_chg: float | None = None
        self.prev_close: float | None = None
        self.pos = 0                     # signed, from broker fills
        self.entry_px: float | None = None
        self.extreme: float | None = None
        self.last_stop: float | None = None
        self._flattened = False
        self.executor = None             # injected by _attach_order_path
        self.stats = {"bars": 0, "signals": 0, "entries_sent": 0,
                      "stop_mods": 0, "nacks": 0}

    # ---- broker events (UserSyncRouter path) ----

    async def on_fill(self, side: str, qty: int, price: float,
                      fee: float = 0.0) -> None:
        signed = qty if side == "buy" else -qty
        was_flat = self.pos == 0
        self.pos += signed
        if was_flat and self.pos != 0:
            self.entry_px = price
            self.extreme = price
            self.last_stop = None
            log.info("POSITION OPEN %+d @ %.2f", self.pos, price)
        elif self.pos == 0:
            self.entry_px = self.extreme = self.last_stop = None
            log.info("POSITION FLAT (fill %s %d @ %.2f)", side, qty, price)

    async def on_order_nack(self, error: str = "") -> None:
        self.stats["nacks"] += 1
        log.warning("NACK: %s", error)

    # ---- market data (DatabentoFeed on_trade) ----

    async def on_trade(self, price: float, size: float, side: str,
                       ts_ns: int | None = None) -> None:
        ts = ts_ns if ts_ns is not None else int(
            self.now_fn().timestamp() * 1e9)
        closed = self.bars.on_trade(ts, price)
        if closed is not None:
            await self._on_bar_close(closed)

    async def _on_bar_close(self, bar: Bar) -> None:
        self.stats["bars"] += 1
        now = self.now_fn()
        chg = (bar.close - self.prev_close
               if self.prev_close is not None else None)
        prev_chg, self.prev_chg = self.prev_chg, chg
        self.prev_close = bar.close

        # session flatten first — unconditional
        if self.session.should_flatten(now):
            if not self._flattened:
                self._flattened = True
                await self.executor.cancel_working(
                    self.contract_symbol, "session close")
                if self.pos != 0:
                    await self.executor.flatten(
                        self.contract_symbol, "session close 15:55 ET")
            return
        self._flattened = False

        if self.pos != 0:
            await self._manage(bar)
        elif self.session.is_entry_allowed(now) and chg is not None \
                and prev_chg is not None:
            if chg > 0 and prev_chg > 0 and (chg + prev_chg) >= self.trigger:
                await self._enter("buy", bar.close)
            elif chg < 0 and prev_chg < 0 \
                    and -(chg + prev_chg) >= self.trigger:
                await self._enter("sell", bar.close)

    async def _enter(self, side: str, close: float) -> None:
        self.stats["signals"] += 1
        sign = 1 if side == "buy" else -1
        limit = close + sign * 2 * self.tick          # marketable limit
        stop = close - sign * self.init_dist
        sent = await self.executor.enter(self.contract_symbol, side, 1,
                                         limit, stop)
        if sent:
            self.stats["entries_sent"] += 1
            log.info("ENTRY sent: %s limit %.2f bracket stop %.2f",
                     side.upper(), limit, stop)

    async def _manage(self, bar: Bar) -> None:
        if self.pos > 0:
            self.extreme = max(self.extreme or bar.high, bar.high)
            new_stop = self.extreme - self.trail
            better = self.last_stop is None or new_stop > self.last_stop
        else:
            self.extreme = min(self.extreme or bar.low, bar.low)
            new_stop = self.extreme + self.trail
            better = self.last_stop is None or new_stop < self.last_stop
        if better and (self.last_stop is None
                       or abs(new_stop - self.last_stop) >= self.tick):
            self.last_stop = new_stop
            self.stats["stop_mods"] += 1
            await self.executor.modify_stop(self.contract_symbol, new_stop)
