"""Tick-native quadrant trailing SL/TP (§13) — ported from the kraken
RiskManager, USD arithmetic replaced by the product's quadrant geometry.

Geometry comes from the product risk block (risk_reward_ratio ×
trail_step_pct → QuadrantGeometry). Milestone k fires when price has moved
k × trail_step ticks in favor; the stop then moves to entry +
(k−1) × trail_step ticks (k=1 → break-even). The stop only ever ratchets
toward profit. Milestone n_steps == the target: full exit. Shorts mirror.

The stop is enforced server-side (OSO bracket); on_price_update() reports
when the resting stop must be MODIFIED upward, and catches SL/TP as a
belt-and-braces local check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.config_loader import Product, QuadrantGeometry
from src.utils.logger import get_logger

ExitReason = Literal["sl", "tp", "none"]


def round_to_tick(price: float, tick_size: float) -> float:
    return round(round(price / tick_size) * tick_size, 10)


@dataclass
class PositionRisk:
    symbol: str              # active contract, e.g. 'YMU6'
    side: str                # 'buy' (long) or 'sell' (short)
    entry_price: float
    qty: int
    geometry: QuadrantGeometry
    tick_size: float

    sl_price: float = field(init=False)
    tp_price: float = field(init=False)
    milestones_hit: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        sign = 1 if self.side == "buy" else -1
        self.sl_price = round_to_tick(
            self.entry_price - sign * self.geometry.stop_ticks * self.tick_size,
            self.tick_size)
        self.tp_price = round_to_tick(
            self.entry_price + sign * self.geometry.tp_ticks * self.tick_size,
            self.tick_size)

    def gain_ticks(self, price: float) -> float:
        sign = 1 if self.side == "buy" else -1
        return sign * (price - self.entry_price) / self.tick_size


@dataclass(frozen=True)
class RiskUpdate:
    reason: ExitReason       # 'sl' | 'tp' | 'none'
    price: float
    new_stop: float | None   # set when the resting stop order must be modified


class RiskManager:
    """Per-product risk state; one open PositionRisk per symbol."""

    def __init__(self, product: Product):
        self.product = product
        self.geometry = product.geometry()
        self._risks: dict[str, PositionRisk] = {}
        self.log = get_logger(__name__)
        self.log.info(
            "RiskManager[%s]: stop=%d ticks  tp=%d ticks  step=%d ticks  (%d steps)",
            product.symbol, self.geometry.stop_ticks, self.geometry.tp_ticks,
            self.geometry.trail_step_ticks, self.geometry.n_steps)

    def on_entry(self, symbol: str, entry_price: float, qty: int, side: str) -> PositionRisk:
        risk = PositionRisk(symbol=symbol, side=side,
                            entry_price=entry_price, qty=qty,
                            geometry=self.geometry,
                            tick_size=self.product.tick_size)
        self._risks[symbol] = risk
        self.log.info("Risk entry %s %s %d @ %.2f  SL=%.2f  TP=%.2f",
                      side.upper(), symbol, qty, entry_price,
                      risk.sl_price, risk.tp_price)
        return risk

    def on_exit(self, symbol: str) -> None:
        self._risks.pop(symbol, None)

    def has_position(self, symbol: str) -> bool:
        return symbol in self._risks

    def get_risk(self, symbol: str) -> PositionRisk | None:
        return self._risks.get(symbol)

    def on_price_update(self, symbol: str, price: float) -> RiskUpdate:
        risk = self._risks.get(symbol)
        if risk is None:
            return RiskUpdate("none", price, None)

        sign = 1 if risk.side == "buy" else -1
        gain = risk.gain_ticks(price)

        # target reached — full exit (§13)
        if gain >= self.geometry.tp_ticks:
            self.log.info("TP hit %s @ %.2f (+%d ticks)", symbol, price,
                          self.geometry.tp_ticks)
            return RiskUpdate("tp", price, None)

        # quadrant milestone — ratchet the stop one step behind price
        new_stop = None
        if gain > 0:
            milestones = min(int(gain // self.geometry.trail_step_ticks),
                             self.geometry.n_steps - 1)
            if milestones > risk.milestones_hit:
                risk.milestones_hit = milestones
                candidate = round_to_tick(
                    risk.entry_price + sign * (milestones - 1)
                    * self.geometry.trail_step_ticks * self.tick_size_of(risk),
                    risk.tick_size)
                if sign * (candidate - risk.sl_price) > 0:   # ratchet only
                    self.log.info(
                        "Quadrant %d/%d %s: SL %.2f → %.2f%s",
                        milestones, self.geometry.n_steps, symbol,
                        risk.sl_price, candidate,
                        "  [break-even]" if milestones == 1 else "")
                    risk.sl_price = candidate
                    new_stop = candidate

        # local stop check (server-side stop is the real enforcement)
        if sign * (price - risk.sl_price) <= 0:
            self.log.info("SL hit %s @ %.2f (stop %.2f)", symbol, price,
                          risk.sl_price)
            return RiskUpdate("sl", price, None)

        return RiskUpdate("none", price, new_stop)

    @staticmethod
    def tick_size_of(risk: PositionRisk) -> float:
        return risk.tick_size
