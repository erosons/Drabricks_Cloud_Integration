import zlib
from typing import Optional

from sortedcontainers import SortedDict

from ..utils.logger import get_logger


class OrderBook:
    """
    Level-2 order book for a single symbol.

    Bids are stored descending (best bid first).
    Asks are stored ascending (best ask first).

    Raw string representations of price/qty are preserved alongside float values
    so the Kraken CRC32 checksum can be computed correctly (trailing zeros matter).
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        # negative-key trick: SortedDict sorts ascending, so negating price gives descending bids
        self.bids: SortedDict = SortedDict(lambda p: -p)
        self.asks: SortedDict = SortedDict()
        # raw string tuples (price_str, qty_str) keyed by float price — used only for checksum
        self._bid_str: dict[float, tuple[str, str]] = {}
        self._ask_str: dict[float, tuple[str, str]] = {}
        self.log = get_logger(__name__)

    # ------------------------------------------------------------------
    # Book maintenance
    # ------------------------------------------------------------------

    def apply_snapshot(self, data: dict) -> None:
        self.bids.clear()
        self.asks.clear()
        self._bid_str.clear()
        self._ask_str.clear()
        for lvl in data.get("bids", []):
            p, q = float(lvl["price"]), float(lvl["qty"])
            self.bids[p] = q
            self._bid_str[p] = (str(lvl["price"]), str(lvl["qty"]))
        for lvl in data.get("asks", []):
            p, q = float(lvl["price"]), float(lvl["qty"])
            self.asks[p] = q
            self._ask_str[p] = (str(lvl["price"]), str(lvl["qty"]))

    def apply_update(self, data: dict) -> None:
        for lvl in data.get("bids", []):
            price, qty = float(lvl["price"]), float(lvl["qty"])
            if qty == 0:
                self.bids.pop(price, None)
                self._bid_str.pop(price, None)
            else:
                self.bids[price] = qty
                self._bid_str[price] = (str(lvl["price"]), str(lvl["qty"]))
        for lvl in data.get("asks", []):
            price, qty = float(lvl["price"]), float(lvl["qty"])
            if qty == 0:
                self.asks.pop(price, None)
                self._ask_str.pop(price, None)
            else:
                self.asks[price] = qty
                self._ask_str[price] = (str(lvl["price"]), str(lvl["qty"]))

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def best_bid(self) -> Optional[tuple[float, float]]:
        if self.bids:
            p = self.bids.keys()[0]
            return p, self.bids[p]
        return None

    def best_ask(self) -> Optional[tuple[float, float]]:
        if self.asks:
            p = self.asks.keys()[0]
            return p, self.asks[p]
        return None

    def mid_price(self) -> Optional[float]:
        bb, ba = self.best_bid(), self.best_ask()
        if bb and ba:
            return (bb[0] + ba[0]) / 2.0
        return None

    def spread(self) -> Optional[float]:
        bb, ba = self.best_bid(), self.best_ask()
        if bb and ba:
            return ba[0] - bb[0]
        return None

    def spread_bps(self) -> Optional[float]:
        mid = self.mid_price()
        sp = self.spread()
        if mid and sp:
            return (sp / mid) * 10_000
        return None

    def bid_volume(self, levels: int = 10) -> float:
        return sum(qty for _, qty in list(self.bids.items())[:levels])

    def ask_volume(self, levels: int = 10) -> float:
        return sum(qty for _, qty in list(self.asks.items())[:levels])

    def imbalance(self, levels: int = 10) -> float:
        """
        Order book imbalance in [-1, +1].
        +1 means all volume is on bid side (bullish pressure).
        -1 means all volume is on ask side (bearish pressure).
        """
        bv = self.bid_volume(levels)
        av = self.ask_volume(levels)
        total = bv + av
        if total == 0:
            return 0.0
        return (bv - av) / total

    # ------------------------------------------------------------------
    # Checksum validation (Kraken CRC32 format)
    # ------------------------------------------------------------------

    def validate_checksum(self, checksum: int) -> bool:
        """
        Validate CRC32 checksum of top-10 bids and asks.
        Uses original string representations from exchange to preserve trailing zeros.
        Format: concatenate (price_no_decimal + qty_no_decimal) for each level.
        NOTE: Kraken v2 exact checksum spec not fully published; mismatch logged at DEBUG only.
        """
        parts: list[str] = []
        for price in list(self.bids.keys())[:10]:
            ps, qs = self._bid_str.get(price, (str(price), str(self.bids[price])))
            parts.append(_strip_decimal(ps))
            parts.append(_strip_decimal(qs))
        for price in list(self.asks.keys())[:10]:
            ps, qs = self._ask_str.get(price, (str(price), str(self.asks[price])))
            parts.append(_strip_decimal(ps))
            parts.append(_strip_decimal(qs))
        crc = zlib.crc32("".join(parts).encode()) & 0xFFFFFFFF
        valid = crc == checksum
        if not valid:
            self.log.debug("Checksum mismatch: computed=%d expected=%d", crc, checksum)
        return valid

    def __repr__(self) -> str:
        bb = self.best_bid()
        ba = self.best_ask()
        return (
            f"<OrderBook {self.symbol} "
            f"bid={bb[0] if bb else '?'} ask={ba[0] if ba else '?'} "
            f"spread={self.spread() or '?'} "
            f"imbalance={self.imbalance():.3f}>"
        )


def _strip_decimal(s: str) -> str:
    return s.replace(".", "").lstrip("0") or "0"
