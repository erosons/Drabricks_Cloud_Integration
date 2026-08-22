"""Success-rate monitoring: win/loss counters + the v_round_trips view.

Two sources by design (§15): Prometheus counters are the disposable live
view (reset on restart), the fills-derived v_round_trips view is the
of-record history. These tests pin both to the same classification rule:
win = realized P&L net of fees ≥ 0 at round-trip close.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from prometheus_client import REGISTRY

from src.config_loader import load_config
from src.market_data.orderbook import OrderBook
from src.storage.db import Database
from src.trading.order_flow import (
    DryRunExecutor,
    FuturesOrderFlowStrategy,
    OrderFlowAnalyzer,
)
from src.trading.position import PositionTracker
from src.trading.risk import RiskManager

CONFIG = load_config(str(Path(__file__).parent.parent / "config"))
MES = CONFIG.products["MES"]


class _AlwaysOpen:
    def is_entry_allowed(self, now):
        return True

    def should_flatten(self, now):
        return False


class _NoNews:
    def entering_blackout(self, prev, now):
        return None

    def active_blackout(self, now):
        return None


def _engine():
    engine = FuturesOrderFlowStrategy(
        product=MES,
        contract_symbol="MESU6",
        analyzer=OrderFlowAnalyzer(imbalance_threshold=0.1, min_confidence=0.5),
        price_action=None,
        risk_manager=RiskManager(MES),
        position_tracker=PositionTracker(MES.tick_size, MES.tick_value),
        executor=DryRunExecutor("MES"),
        session_manager=_AlwaysOpen(),
        news_guard=_NoNews(),
        now_fn=lambda: datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc),
    )
    engine.attach_orderbook(OrderBook("MESU6", MES.tick_size))
    return engine


def _counter(name: str) -> float:
    return REGISTRY.get_sample_value(name, {"product": "MES"}) or 0.0


class TestWinLossCounters:
    def test_profitable_round_trip_counts_as_win(self):
        engine, won0 = _engine(), _counter("bot_trades_won_total")
        asyncio.run(engine.on_fill("buy", 1, 6400.00))
        asyncio.run(engine.on_fill("sell", 1, 6403.00))   # +12 ticks
        assert _counter("bot_trades_won_total") == won0 + 1

    def test_losing_round_trip_counts_as_loss(self):
        engine, lost0 = _engine(), _counter("bot_trades_lost_total")
        asyncio.run(engine.on_fill("sell", 1, 6400.00))
        asyncio.run(engine.on_fill("buy", 1, 6402.00))    # short, price rose
        assert _counter("bot_trades_lost_total") == lost0 + 1

    def test_fees_can_turn_scratch_into_loss(self):
        engine, lost0 = _engine(), _counter("bot_trades_lost_total")
        asyncio.run(engine.on_fill("buy", 1, 6400.00, fee=1.10))
        asyncio.run(engine.on_fill("sell", 1, 6400.00, fee=1.10))
        assert _counter("bot_trades_lost_total") == lost0 + 1

    def test_profitable_trailed_stop_is_a_win_not_a_loss(self):
        # the quadrant trail exits winners via the stop — classification
        # must come from P&L, never from which bracket leg fired
        engine, won0 = _engine(), _counter("bot_trades_won_total")
        lost0 = _counter("bot_trades_lost_total")
        asyncio.run(engine.on_fill("buy", 1, 6400.00))
        asyncio.run(engine.on_fill("sell", 1, 6401.50))   # trailed stop, +6 ticks
        assert _counter("bot_trades_won_total") == won0 + 1
        assert _counter("bot_trades_lost_total") == lost0

    def test_partial_fills_count_one_round_trip(self):
        engine, won0 = _engine(), _counter("bot_trades_won_total")
        asyncio.run(engine.on_fill("buy", 2, 6400.00))
        asyncio.run(engine.on_fill("sell", 1, 6402.00))
        asyncio.run(engine.on_fill("sell", 1, 6403.00))
        assert _counter("bot_trades_won_total") == won0 + 1

    def test_second_trip_measured_from_its_own_base(self):
        engine = _engine()
        won0, lost0 = (_counter("bot_trades_won_total"),
                       _counter("bot_trades_lost_total"))
        asyncio.run(engine.on_fill("buy", 1, 6400.00))
        asyncio.run(engine.on_fill("sell", 1, 6410.00))   # big win
        asyncio.run(engine.on_fill("buy", 1, 6410.00))
        asyncio.run(engine.on_fill("sell", 1, 6409.00))   # small loss
        assert _counter("bot_trades_won_total") == won0 + 1
        assert _counter("bot_trades_lost_total") == lost0 + 1

    def test_nack_increments_rejected(self):
        engine, rej0 = _engine(), _counter("bot_orders_rejected_total")
        asyncio.run(engine.on_order_nack("MaxOrderQtyLimitReached"))
        assert _counter("bot_orders_rejected_total") == rej0 + 1


class TestRoundTripsView:
    def _db(self, tmp_path):
        return Database(tmp_path / "t.db")

    def test_win_and_loss_trips(self, tmp_path):
        db = self._db(tmp_path)
        db.record_fill("MES", "MESU6", "buy", 1, 6400.00, 1.10)
        db.record_fill("MES", "MESU6", "sell", 1, 6403.00, 1.10)   # +3 pts
        db.record_fill("MES", "MESU6", "sell", 1, 6403.00, 1.10)
        db.record_fill("MES", "MESU6", "buy", 1, 6404.00, 1.10)    # −1 pt
        rows = db.conn.execute(
            "SELECT closed, points_pnl, usd_pnl FROM v_round_trips "
            "ORDER BY trip_no").fetchall()
        assert len(rows) == 2
        assert rows[0]["closed"] == 1
        assert abs(rows[0]["points_pnl"] - 3.0) < 1e-9
        assert abs(rows[0]["usd_pnl"] - (3.0 * 5.0 - 2.20)) < 1e-9   # win
        assert abs(rows[1]["usd_pnl"] - (-1.0 * 5.0 - 2.20)) < 1e-9  # loss

    def test_open_trip_flagged_not_closed(self, tmp_path):
        db = self._db(tmp_path)
        db.record_fill("MES", "MESU6", "buy", 1, 6400.00, 1.10)
        row = db.conn.execute("SELECT closed FROM v_round_trips").fetchone()
        assert row["closed"] == 0

    def test_partial_close_stays_one_trip(self, tmp_path):
        db = self._db(tmp_path)
        db.record_fill("MES", "MESU6", "buy", 2, 6400.00, 2.20)
        db.record_fill("MES", "MESU6", "sell", 1, 6402.00, 1.10)
        db.record_fill("MES", "MESU6", "sell", 1, 6403.00, 1.10)
        rows = db.conn.execute("SELECT * FROM v_round_trips").fetchall()
        assert len(rows) == 1
        assert rows[0]["closed"] == 1
        assert abs(rows[0]["points_pnl"] - 5.0) < 1e-9

    def test_products_partition_independently(self, tmp_path):
        db = self._db(tmp_path)
        db.record_fill("MES", "MESU6", "buy", 1, 6400.00, 0.0)
        db.record_fill("MNQ", "MNQU6", "buy", 1, 23000.00, 0.0)
        db.record_fill("MES", "MESU6", "sell", 1, 6401.00, 0.0)
        db.record_fill("MNQ", "MNQU6", "sell", 1, 23010.00, 0.0)
        rows = db.conn.execute(
            "SELECT product, usd_pnl FROM v_round_trips ORDER BY product"
        ).fetchall()
        assert [r["product"] for r in rows] == ["MES", "MNQ"]
        assert abs(rows[0]["usd_pnl"] - 5.0) < 1e-9    # 1 pt × $5
        assert abs(rows[1]["usd_pnl"] - 20.0) < 1e-9   # 10 pts × $2
