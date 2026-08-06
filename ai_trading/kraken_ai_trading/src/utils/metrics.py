"""
Prometheus metrics for one bot process.

Each pair runs its own process on a distinct port (METRICS_PORT env var).
Call BotMetrics.update_*() from order_flow.py after every relevant event.
"""

import os
from prometheus_client import Counter, Gauge, start_http_server

_started = False


def start_metrics_server() -> None:
    global _started
    port = int(os.getenv("METRICS_PORT", "0"))
    if port and not _started:
        try:
            start_http_server(port)
            _started = True
        except OSError:
            # Port still held by a previous process — metrics will be unavailable
            # this session, but the bot continues trading normally.
            import logging
            logging.getLogger(__name__).warning(
                "METRICS_PORT %d already in use — metrics disabled for this session", port
            )


# -- EMA / price -------------------------------------------------------
fast_ema_gauge = Gauge("bot_fast_ema", "Fast EMA value", ["pair"])
slow_ema_gauge = Gauge("bot_slow_ema", "Slow EMA value", ["pair"])
mid_price_gauge = Gauge("bot_mid_price", "Order-book mid price", ["pair"])

# -- Signal / exhaustion -----------------------------------------------
signal_gauge = Gauge("bot_signal", "Active signal (1=buy 0=neutral -1=sell)", ["pair"])
exhaustion_gauge = Gauge("bot_exhaustion_active", "1 if exhaustion signal is active", ["pair"])

# -- Position / PnL ----------------------------------------------------
position_qty_gauge = Gauge("bot_position_qty", "Current base-asset position", ["pair"])
sl_price_gauge = Gauge("bot_sl_price", "Current stop-loss price", ["pair"])
tp_price_gauge = Gauge("bot_tp_price", "Current take-profit price", ["pair"])
unrealized_pnl_gauge = Gauge("bot_unrealized_pnl_usd", "Unrealized PnL in USD", ["pair"])
realized_pnl_gauge = Gauge("bot_realized_pnl_usd", "Realized PnL in USD (session)", ["pair"])

# -- Order counters ----------------------------------------------------
orders_placed_counter = Counter("bot_orders_placed_total", "Limit orders posted", ["pair"])
orders_filled_counter = Counter("bot_orders_filled_total", "Orders fully filled", ["pair"])
orders_cancelled_counter = Counter("bot_orders_cancelled_total", "Orders cancelled", ["pair"])
sl_hits_counter = Counter("bot_sl_hits_total", "Stop-loss exits triggered", ["pair"])
tp_hits_counter = Counter("bot_tp_hits_total", "Take-profit exits triggered", ["pair"])


class BotMetrics:
    """Thin wrapper that pins a pair label to every metric."""

    def __init__(self, pair: str) -> None:
        self.pair = pair

    # EMA / price
    def update_emas(self, fast: float, slow: float, mid: float) -> None:
        fast_ema_gauge.labels(self.pair).set(fast)
        slow_ema_gauge.labels(self.pair).set(slow)
        mid_price_gauge.labels(self.pair).set(mid)

    # Signal
    def update_signal(self, signal_str: str, exhaustion_active: bool) -> None:
        _val = {"buy": 1, "sell": -1}.get(signal_str, 0)
        signal_gauge.labels(self.pair).set(_val)
        exhaustion_gauge.labels(self.pair).set(1 if exhaustion_active else 0)

    # Position / risk
    def update_position(self, qty: float, sl: float, tp: float) -> None:
        position_qty_gauge.labels(self.pair).set(qty)
        sl_price_gauge.labels(self.pair).set(sl)
        tp_price_gauge.labels(self.pair).set(tp)

    # PnL
    def update_pnl(self, realized: float, unrealized: float) -> None:
        realized_pnl_gauge.labels(self.pair).set(realized)
        unrealized_pnl_gauge.labels(self.pair).set(unrealized)

    # Counters (increment-only)
    def inc_orders_placed(self) -> None:
        orders_placed_counter.labels(self.pair).inc()

    def inc_orders_filled(self) -> None:
        orders_filled_counter.labels(self.pair).inc()

    def inc_orders_cancelled(self) -> None:
        orders_cancelled_counter.labels(self.pair).inc()

    def inc_sl_hit(self) -> None:
        sl_hits_counter.labels(self.pair).inc()

    def inc_tp_hit(self) -> None:
        tp_hits_counter.labels(self.pair).inc()
