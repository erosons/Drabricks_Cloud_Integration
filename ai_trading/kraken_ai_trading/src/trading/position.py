from dataclasses import dataclass, field

from ..utils.logger import get_logger


@dataclass
class Position:
    symbol: str
    qty: float = 0.0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    mark_price: float = 0.0
    total_fees: float = 0.0

    @property
    def notional(self) -> float:
        return self.qty * self.mark_price if self.mark_price else self.qty * self.avg_price

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl


class PositionTracker:
    """
    Tracks positions and P&L across fills.
    Supports only long spot positions (qty >= 0).
    """

    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}
        self.log = get_logger(__name__)

    def get_position(self, symbol: str) -> Position:
        if symbol not in self._positions:
            self._positions[symbol] = Position(symbol=symbol)
        return self._positions[symbol]

    def on_fill(self, symbol: str, side: str, qty: float, price: float, fee: float = 0.0) -> None:
        pos = self.get_position(symbol)
        pos.total_fees += fee

        if side == "buy":
            total_cost = pos.qty * pos.avg_price + qty * price
            pos.qty += qty
            pos.avg_price = total_cost / pos.qty if pos.qty > 0 else 0.0
        else:
            filled_qty = min(qty, pos.qty)
            realized = (price - pos.avg_price) * filled_qty - fee
            pos.realized_pnl += realized
            pos.qty = max(0.0, pos.qty - filled_qty)
            if pos.qty == 0:
                pos.avg_price = 0.0

        if pos.mark_price == 0:
            pos.mark_price = price

        self.log.info(
            "Fill %s %s %.8f @ %.4f | pos=%.8f avg=%.4f rpnl=%.4f",
            side.upper(), symbol, qty, price, pos.qty, pos.avg_price, pos.realized_pnl,
        )

    def update_mark_price(self, symbol: str, price: float) -> None:
        pos = self.get_position(symbol)
        pos.mark_price = price
        if pos.qty > 0 and pos.avg_price > 0:
            pos.unrealized_pnl = (price - pos.avg_price) * pos.qty

    def seed_position(self, symbol: str, qty: float, mark_price: float) -> None:
        """Seed initial position from exchange balance on startup (avg_price unknown, use mark)."""
        pos = self.get_position(symbol)
        pos.qty = qty
        pos.avg_price = mark_price
        pos.mark_price = mark_price
        self.log.info("Seeded position %s  qty=%.8f  mark=%.4f", symbol, qty, mark_price)

    def get_open_positions(self) -> dict[str, Position]:
        return {s: p for s, p in self._positions.items() if p.qty > 0}

    def get_total_pnl(self) -> tuple[float, float]:
        """Returns (realized_pnl, unrealized_pnl)."""
        rpnl = sum(p.realized_pnl for p in self._positions.values())
        upnl = sum(p.unrealized_pnl for p in self._positions.values())
        return rpnl, upnl

    def summary(self) -> str:
        rpnl, upnl = self.get_total_pnl()
        lines = [f"{'Symbol':<12} {'Qty':>12} {'AvgPx':>10} {'Mark':>10} {'uPnL':>10} {'rPnL':>10}"]
        for p in self._positions.values():
            if p.qty > 0:
                lines.append(
                    f"{p.symbol:<12} {p.qty:>12.6f} {p.avg_price:>10.4f} "
                    f"{p.mark_price:>10.4f} {p.unrealized_pnl:>10.4f} {p.realized_pnl:>10.4f}"
                )
        lines.append(f"\nTotal  rPnL={rpnl:.4f}  uPnL={upnl:.4f}")
        return "\n".join(lines)
