"""Tick-indexed DOM book for one contract (§18).

Fed by md/subscribeDOM events. Tradovate may coalesce frames across symbols
and drop stale intermediate updates under load (attestation #24–25), so this
book is snapshot-oriented: every DOM event carries the full visible depth,
and anything that looks like a gap is handled by drop-and-resync — callers
see `synced == False` until the next full snapshot lands.
"""

from __future__ import annotations

from src.utils.logger import get_logger


class OrderBook:
    def __init__(self, symbol: str, tick_size: float):
        self.symbol = symbol
        self.tick_size = tick_size
        self.bids: list[tuple[float, int]] = []   # (price, size) best-first
        self.asks: list[tuple[float, int]] = []
        self.synced = False
        self.log = get_logger(__name__)

    def apply_dom(self, data: dict) -> None:
        """Apply one DOM event: {"bids": [{"price", "size"}...], "asks": [...]}.
        Tradovate DOM events are full visible-depth snapshots."""
        try:
            bids = [(float(l["price"]), int(l["size"])) for l in data.get("bids", [])]
            asks = [(float(l["price"]), int(l["size"])) for l in data.get("asks", [])]
        except (KeyError, TypeError, ValueError) as exc:
            self.desync(f"malformed DOM event: {exc}")
            return
        self.bids = sorted((l for l in bids if l[1] > 0), key=lambda l: -l[0])
        self.asks = sorted((l for l in asks if l[1] > 0), key=lambda l: l[0])
        self.synced = bool(self.bids and self.asks)

    def desync(self, reason: str) -> None:
        """Gap detected — drop the book until the next snapshot (§17)."""
        self.log.warning("[%s] book desync: %s", self.symbol, reason)
        self.bids, self.asks = [], []
        self.synced = False

    # ---- queries (None/0 when not synced) ----

    def best_bid(self) -> tuple[float, int] | None:
        return self.bids[0] if self.synced and self.bids else None

    def best_ask(self) -> tuple[float, int] | None:
        return self.asks[0] if self.synced and self.asks else None

    def mid_price(self) -> float | None:
        bb, ba = self.best_bid(), self.best_ask()
        return (bb[0] + ba[0]) / 2.0 if bb and ba else None

    def spread_ticks(self) -> float | None:
        bb, ba = self.best_bid(), self.best_ask()
        return (ba[0] - bb[0]) / self.tick_size if bb and ba else None

    def imbalance(self, levels: int = 10) -> float:
        """(bid_vol − ask_vol) / total over the top N levels, in [−1, +1]."""
        bid_vol = sum(size for _, size in self.bids[:levels])
        ask_vol = sum(size for _, size in self.asks[:levels])
        total = bid_vol + ask_vol
        return (bid_vol - ask_vol) / total if total else 0.0
