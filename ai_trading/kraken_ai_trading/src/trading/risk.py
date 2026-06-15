"""
Progressive trailing stop / take profit risk manager.

Rules (long position, entry price E):
  - Hard SL = E − stop_loss_usd
  - TP      = E + stop_loss_usd * risk_reward_ratio   (default 3:1 → +$90)
  - trail_step = TP range * trail_step_pct             (default 25% → $22.50)

Milestone progression (milestones_hit = int(gain / trail_step)):
  - 0 milestones : SL stays at E − stop_loss_usd
  - 1 milestone  : SL → E               (break-even)
  - 2 milestones : SL → E + trail_step
  - 3 milestones : SL → E + 2*trail_step
  - 4 milestones : TP hit → exit        (gain >= TP range)

SL only ever advances (never retreats).
Short-side mirror: all inequalities flip.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional

from ..utils.logger import get_logger

ExitReason = Literal["sl", "tp", "none"]


@dataclass
class PositionRisk:
    symbol: str
    side: str            # "buy" or "sell"
    entry_price: float
    qty: float
    stop_loss_usd: float
    take_profit_usd: float
    trail_step_usd: float

    # computed at entry
    sl_price: float = field(init=False)
    tp_price: float = field(init=False)
    milestones_hit: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        # Convert total-USD risk to per-unit price levels
        sl_per_unit = self.stop_loss_usd / self.qty
        tp_per_unit = self.take_profit_usd / self.qty
        if self.side == "buy":
            self.sl_price = self.entry_price - sl_per_unit
            self.tp_price = self.entry_price + tp_per_unit
        else:
            self.sl_price = self.entry_price + sl_per_unit
            self.tp_price = self.entry_price - tp_per_unit


class RiskManager:
    """
    Tracks per-symbol risk state and emits SL/TP exit signals on each price update.

    Usage:
        rm = RiskManager(stop_loss_usd=30.0, risk_reward_ratio=3.0, trail_step_pct=0.25)
        rm.on_entry("BTC/USD", entry_price=70_000.0, qty=0.001, side="buy")
        reason, exit_price = rm.on_price_update("BTC/USD", current_price)
        if reason != "none":
            rm.on_exit("BTC/USD")
            # submit market-sell order
    """

    def __init__(
        self,
        stop_loss_usd: float = 30.0,
        risk_reward_ratio: float = 3.0,
        trail_step_pct: float = 0.25,
        take_profit_usd: float = 0.0,   # direct override — used when PROFIT_TARGET_PCT is set
    ) -> None:
        self.stop_loss_usd = stop_loss_usd
        # Direct USD target takes priority over ratio-based calculation
        self.take_profit_usd = take_profit_usd if take_profit_usd > 0 else stop_loss_usd * risk_reward_ratio
        self.trail_step_usd = self.take_profit_usd * trail_step_pct
        self._risks: dict[str, PositionRisk] = {}
        self.log = get_logger(__name__)

        self.log.info(
            "RiskManager init: SL=$%.2f  TP=$%.4f  trail_step=$%.4f  (25%%=$%.4f  50%%=$%.4f  75%%=$%.4f)",
            self.stop_loss_usd,
            self.take_profit_usd,
            self.trail_step_usd,
            self.trail_step_usd * 1,
            self.trail_step_usd * 2,
            self.trail_step_usd * 3,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_entry(self, symbol: str, entry_price: float, qty: float, side: str) -> None:
        risk = PositionRisk(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            qty=qty,
            stop_loss_usd=self.stop_loss_usd,
            take_profit_usd=self.take_profit_usd,
            trail_step_usd=self.trail_step_usd,
        )
        self._risks[symbol] = risk
        self.log.info(
            "Risk entry  %s %s qty=%.4f @ %.4f  SL=%.4f ($%.2f)  TP=%.4f ($%.2f)",
            side.upper(), symbol, qty, entry_price,
            risk.sl_price, self.stop_loss_usd,
            risk.tp_price, self.take_profit_usd,
        )

    def on_price_update(self, symbol: str, price: float) -> tuple[ExitReason, float]:
        """
        Check SL/TP for the open position in `symbol`.

        Returns ("sl"|"tp"|"none", trigger_price).
        Advances trailing stop if a new milestone is hit.
        """
        risk = self._risks.get(symbol)
        if risk is None:
            return "none", price

        if risk.side == "buy":
            return self._check_long(risk, price)
        return self._check_short(risk, price)

    def on_exit(self, symbol: str) -> None:
        self._risks.pop(symbol, None)
        self.log.info("Risk state cleared for %s", symbol)

    def has_position(self, symbol: str) -> bool:
        return symbol in self._risks

    def get_risk(self, symbol: str) -> Optional[PositionRisk]:
        return self._risks.get(symbol)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_long(self, risk: PositionRisk, price: float) -> tuple[ExitReason, float]:
        gain_per_unit = price - risk.entry_price
        gain_usd = gain_per_unit * risk.qty
        tp_per_unit = risk.take_profit_usd / risk.qty
        trail_per_unit = risk.trail_step_usd / risk.qty

        # TP hit
        if gain_per_unit >= tp_per_unit:
            self.log.info(
                "TP hit  %s  price=%.4f  gain=+$%.2f  entry=%.4f",
                risk.symbol, price, gain_usd, risk.entry_price,
            )
            return "tp", price

        # Advance trailing stop
        if gain_per_unit > 0 and trail_per_unit > 0:
            milestones = int(gain_per_unit / trail_per_unit)
            if milestones > risk.milestones_hit:
                risk.milestones_hit = milestones
                # milestone 1 → break-even; each additional → advance by trail_step
                new_sl = risk.entry_price + max(0, milestones - 1) * trail_per_unit
                if new_sl > risk.sl_price:
                    old_sl = risk.sl_price
                    risk.sl_price = new_sl
                    self.log.info(
                        "Trail SL advanced  %s  milestone=%d  SL %.4f → %.4f",
                        risk.symbol, milestones, old_sl, new_sl,
                    )

        # SL hit
        if price <= risk.sl_price:
            self.log.info(
                "SL hit  %s  price=%.4f  sl=%.4f  loss=$%.2f",
                risk.symbol, price, risk.sl_price, (price - risk.entry_price) * risk.qty,
            )
            return "sl", price

        return "none", price

    def _check_short(self, risk: PositionRisk, price: float) -> tuple[ExitReason, float]:
        gain_per_unit = risk.entry_price - price  # positive when price falls (profitable short)
        gain_usd = gain_per_unit * risk.qty
        tp_per_unit = risk.take_profit_usd / risk.qty
        trail_per_unit = risk.trail_step_usd / risk.qty

        # TP hit
        if gain_per_unit >= tp_per_unit:
            self.log.info(
                "TP hit  %s  price=%.4f  gain=+$%.2f  entry=%.4f",
                risk.symbol, price, gain_usd, risk.entry_price,
            )
            return "tp", price

        # Advance trailing stop (SL moves down for shorts)
        if gain_per_unit > 0 and trail_per_unit > 0:
            milestones = int(gain_per_unit / trail_per_unit)
            if milestones > risk.milestones_hit:
                risk.milestones_hit = milestones
                new_sl = risk.entry_price - max(0, milestones - 1) * trail_per_unit
                if new_sl < risk.sl_price:
                    old_sl = risk.sl_price
                    risk.sl_price = new_sl
                    self.log.info(
                        "Trail SL advanced  %s  milestone=%d  SL %.4f → %.4f",
                        risk.symbol, milestones, old_sl, new_sl,
                    )

        # SL hit
        if price >= risk.sl_price:
            self.log.info(
                "SL hit  %s  price=%.4f  sl=%.4f  loss=$%.2f",
                risk.symbol, price, risk.sl_price, (risk.entry_price - price) * risk.qty,
            )
            return "sl", price

        return "none", price
