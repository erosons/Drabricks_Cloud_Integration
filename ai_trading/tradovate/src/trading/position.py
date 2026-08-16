"""Net-position tracker for futures — signed quantity, tick-native P&L (§18).

Unlike the kraken spot tracker this supports symmetric shorts: qty > 0 is
long, qty < 0 is short. P&L is computed in ticks × tick_value — the API
returns raw data only, P&L math is the bot's own responsibility (§17 #17).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.utils.logger import get_logger


@dataclass
class Position:
    symbol: str
    qty: int = 0                 # signed: +long / −short (contracts)
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    mark_price: float = 0.0
    total_fees: float = 0.0

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl


class PositionTracker:
    def __init__(self, tick_size: float, tick_value: float):
        self.tick_size = tick_size
        self.tick_value = tick_value
        self._positions: dict[str, Position] = {}
        self.log = get_logger(__name__)

    def _pnl_usd(self, price_from: float, price_to: float, qty: int) -> float:
        """Signed P&L for closing `qty` (signed) from price_from to price_to."""
        return (price_to - price_from) / self.tick_size * self.tick_value * qty

    def get_position(self, symbol: str) -> Position:
        if symbol not in self._positions:
            self._positions[symbol] = Position(symbol=symbol)
        return self._positions[symbol]

    def on_fill(self, symbol: str, side: str, qty: int, price: float,
                fee: float = 0.0) -> None:
        if side not in ("buy", "sell") or qty <= 0:
            raise ValueError(f"bad fill: side={side!r} qty={qty}")
        pos = self.get_position(symbol)
        pos.total_fees += fee
        signed = qty if side == "buy" else -qty

        if pos.qty == 0 or (pos.qty > 0) == (signed > 0):
            # opening or adding — weighted average entry
            total = pos.qty + signed
            pos.avg_price = ((pos.avg_price * abs(pos.qty) + price * abs(signed))
                             / abs(total))
            pos.qty = total
        else:
            # reducing, closing, or flipping through zero
            closing = min(abs(signed), abs(pos.qty)) * (1 if pos.qty > 0 else -1)
            pos.realized_pnl += self._pnl_usd(pos.avg_price, price, closing) - fee
            remainder = pos.qty + signed
            if remainder == 0:
                pos.qty, pos.avg_price = 0, 0.0
            elif (remainder > 0) == (pos.qty > 0):
                pos.qty = remainder                  # partial close, avg unchanged
            else:
                pos.qty, pos.avg_price = remainder, price   # flipped — new basis

        if pos.mark_price == 0:
            pos.mark_price = price
        self.update_mark_price(symbol, pos.mark_price)
        self.log.info("Fill %s %s %d @ %.2f | pos=%+d avg=%.2f rpnl=%.2f",
                      side.upper(), symbol, qty, price,
                      pos.qty, pos.avg_price, pos.realized_pnl)

    def update_mark_price(self, symbol: str, price: float) -> None:
        pos = self.get_position(symbol)
        pos.mark_price = price
        pos.unrealized_pnl = (self._pnl_usd(pos.avg_price, price, pos.qty)
                              if pos.qty != 0 else 0.0)

    def get_open_positions(self) -> dict[str, Position]:
        return {s: p for s, p in self._positions.items() if p.qty != 0}

    def get_total_pnl(self) -> tuple[float, float]:
        realized = sum(p.realized_pnl for p in self._positions.values())
        unrealized = sum(p.unrealized_pnl for p in self._positions.values())
        return realized, unrealized
