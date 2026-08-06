from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TickerData:
    symbol: str
    bid: float = 0.0
    bid_qty: float = 0.0
    ask: float = 0.0
    ask_qty: float = 0.0
    last: float = 0.0
    volume: float = 0.0
    vwap: float = 0.0
    low: float = 0.0
    high: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0 if self.bid and self.ask else self.last


class TickerFeed:
    def __init__(self) -> None:
        self._tickers: dict[str, TickerData] = {}

    def update(self, data: dict) -> TickerData:
        symbol = data["symbol"]
        ticker = TickerData(
            symbol=symbol,
            bid=float(data.get("bid", 0)),
            bid_qty=float(data.get("bid_qty", 0)),
            ask=float(data.get("ask", 0)),
            ask_qty=float(data.get("ask_qty", 0)),
            last=float(data.get("last", 0)),
            volume=float(data.get("volume", 0)),
            vwap=float(data.get("vwap", 0)),
            low=float(data.get("low", 0)),
            high=float(data.get("high", 0)),
            change=float(data.get("change", 0)),
            change_pct=float(data.get("change_pct", 0)),
        )
        self._tickers[symbol] = ticker
        return ticker

    def get(self, symbol: str) -> Optional[TickerData]:
        return self._tickers.get(symbol)

    def all(self) -> dict[str, TickerData]:
        return dict(self._tickers)
