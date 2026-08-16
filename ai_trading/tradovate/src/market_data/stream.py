"""Market-data event router — MD websocket messages → engine callbacks.

Pure routing (fully testable offline); the socket connection itself is
owned by main.py. Tradovate MD event shapes (⚠ verify at demo soak,
docs/API-document.md): subscription events arrive as
  {"e": "md", "d": {"doms":   [{"contractId": .., "bids": [...], "asks": [...]}]}}
  {"e": "md", "d": {"quotes": [{"contractId": .., "entries": {"Trade": {...}}}]}}
Frames may batch several contracts and drop stale updates (§17 #24–25);
anything unrecognized desyncs the book rather than being guessed at.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from src.market_data.orderbook import OrderBook
from src.utils.logger import get_logger

log = get_logger(__name__)


class MdRouter:
    def __init__(self, book: OrderBook, contract_id: int | None,
                 on_book_update: Callable[[], Awaitable[None]],
                 on_trade: Callable[[float, float, str], Awaitable[None]]):
        self.book = book
        self.contract_id = contract_id      # None = accept all (single-product feed)
        self.on_book_update = on_book_update
        self.on_trade = on_trade

    def _mine(self, item: dict) -> bool:
        return self.contract_id is None or item.get("contractId") == self.contract_id

    async def route(self, msg: dict) -> None:
        if not isinstance(msg, dict) or msg.get("e") != "md":
            return
        data = msg.get("d") or {}

        for dom in data.get("doms", []):
            if not self._mine(dom):
                continue
            self.book.apply_dom(dom)
            await self.on_book_update()

        for quote in data.get("quotes", []):
            if not self._mine(quote):
                continue
            trade = (quote.get("entries") or {}).get("Trade")
            if not trade or "price" not in trade:
                continue
            # Tradovate quotes don't carry aggressor side; infer from the book
            price = float(trade["price"])
            size = float(trade.get("size", 0) or 0)
            best_ask = self.book.best_ask()
            side = "buy" if (best_ask and price >= best_ask[0]) else "sell"
            await self.on_trade(price, size, side)
