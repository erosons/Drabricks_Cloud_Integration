"""Per-product Prometheus metrics (§15) — product N exports on port 8100+N.

BotMetrics keeps the exact call-site interface the engine was ported with.
If prometheus_client is unavailable (stripped-down research env), everything
degrades to a silent no-op so the engine never depends on monitoring.
"""

from __future__ import annotations

from src.utils.logger import get_logger

log = get_logger(__name__)

try:
    from prometheus_client import Counter, Gauge, start_http_server
    _PROM = True
except ImportError:                                   # pragma: no cover
    _PROM = False


def start_metrics_server(port: int) -> None:
    if _PROM:
        start_http_server(port)
        log.info("metrics server on :%d", port)
    else:                                             # pragma: no cover
        log.warning("prometheus_client missing — metrics disabled")


if _PROM:
    # metric families are process-global — register once, label per product
    _FAMILIES = {
        "fast_ema": Gauge("bot_fast_ema", "Fast EMA", ["product"]),
        "slow_ema": Gauge("bot_slow_ema", "Slow EMA", ["product"]),
        "mid": Gauge("bot_mid_price", "Mid price", ["product"]),
        "rpnl": Gauge("bot_realized_pnl_usd", "Realized P&L", ["product"]),
        "upnl": Gauge("bot_unrealized_pnl_usd", "Unrealized P&L", ["product"]),
        "pos": Gauge("bot_position_qty", "Signed net position", ["product"]),
        "sl": Gauge("bot_stop_price", "Current stop", ["product"]),
        "tp": Gauge("bot_target_price", "Current target", ["product"]),
        "signal": Gauge("bot_signal", "-1 sell / 0 neutral / +1 buy", ["product"]),
        "placed": Counter("bot_orders_placed_total", "Orders placed", ["product"]),
        "filled": Counter("bot_orders_filled_total", "Orders filled", ["product"]),
        "rejected": Counter("bot_orders_rejected_total", "Order NACKs", ["product"]),
        "sl_hits": Counter("bot_sl_hits_total", "Stop-loss exits", ["product"]),
        "tp_hits": Counter("bot_tp_hits_total", "Take-profit exits", ["product"]),
        # win/loss = sign of realized P&L (net of fees) when a round trip
        # closes flat — NOT sl/tp hits: a quadrant-trailed stop above
        # break-even exits as an sl_hit but counts as a win here
        "won": Counter("bot_trades_won_total", "Round trips closed ≥ $0", ["product"]),
        "lost": Counter("bot_trades_lost_total", "Round trips closed < $0", ["product"]),
    }


class BotMetrics:
    def __init__(self, product: str):
        self.product = product
        if not _PROM:                                 # pragma: no cover
            return
        m = {k: fam.labels(product=product) for k, fam in _FAMILIES.items()}
        self._fast_ema, self._slow_ema, self._mid = m["fast_ema"], m["slow_ema"], m["mid"]
        self._rpnl, self._upnl = m["rpnl"], m["upnl"]
        self._pos, self._sl, self._tp = m["pos"], m["sl"], m["tp"]
        self._signal = m["signal"]
        self._placed, self._filled = m["placed"], m["filled"]
        self._rejected = m["rejected"]
        self._sl_hits, self._tp_hits = m["sl_hits"], m["tp_hits"]
        self._won, self._lost = m["won"], m["lost"]

    def update_emas(self, fast: float, slow: float, mid: float) -> None:
        if _PROM:
            self._fast_ema.set(fast)
            self._slow_ema.set(slow)
            self._mid.set(mid)

    def update_pnl(self, realized: float, unrealized: float) -> None:
        if _PROM:
            self._rpnl.set(realized)
            self._upnl.set(unrealized)

    def update_position(self, qty: float, sl: float, tp: float) -> None:
        if _PROM:
            self._pos.set(qty)
            self._sl.set(sl)
            self._tp.set(tp)

    def update_signal(self, signal: str, exhaustion_active: bool = False) -> None:
        if _PROM:
            self._signal.set({"buy": 1, "sell": -1}.get(signal, 0))

    def inc_orders_placed(self) -> None:
        if _PROM:
            self._placed.inc()

    def inc_orders_filled(self) -> None:
        if _PROM:
            self._filled.inc()

    def inc_orders_rejected(self) -> None:
        if _PROM:
            self._rejected.inc()

    def inc_trade_closed(self, realized_pnl: float) -> None:
        """One round trip went flat; classify by realized P&L net of fees."""
        if _PROM:
            (self._won if realized_pnl >= 0 else self._lost).inc()

    def inc_sl_hit(self) -> None:
        if _PROM:
            self._sl_hits.inc()

    def inc_tp_hit(self) -> None:
        if _PROM:
            self._tp_hits.inc()
