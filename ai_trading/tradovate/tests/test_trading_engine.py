"""Engine-port tests: tick-native quadrant risk, signed futures positions,
DOM book, and the gated strategy pipeline (all offline)."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.config_loader import load_config
from src.market_data.orderbook import OrderBook
from src.trading.order_flow import (
    DryRunExecutor,
    FuturesOrderFlowStrategy,
    OrderFlowAnalyzer,
)
from src.trading.position import PositionTracker
from src.trading.risk import RiskManager
from src.storage.db import Database

CONFIG = load_config(Path(__file__).resolve().parents[1] / "config")
YM = CONFIG.products["YM"]


class TestQuadrantRisk:
    """The README §13 YM table, verbatim: entry 40,000, stop 39,900,
    quadrants at +75/150/225, TP 40,300."""

    def _risk(self, side="buy"):
        rm = RiskManager(YM)
        rm.on_entry("YMU6", 40_000.0, 1, side)
        return rm

    def test_initial_bracket(self):
        rm = self._risk()
        risk = rm.get_risk("YMU6")
        assert risk.sl_price == 39_900.0
        assert risk.tp_price == 40_300.0

    def test_quadrant_ladder_long(self):
        rm = self._risk()
        assert rm.on_price_update("YMU6", 40_074.0).new_stop is None
        assert rm.on_price_update("YMU6", 40_075.0).new_stop == 40_000.0  # BE
        assert rm.on_price_update("YMU6", 40_150.0).new_stop == 40_075.0
        assert rm.on_price_update("YMU6", 40_225.0).new_stop == 40_150.0
        update = rm.on_price_update("YMU6", 40_300.0)
        assert update.reason == "tp"

    def test_stop_never_retreats(self):
        rm = self._risk()
        rm.on_price_update("YMU6", 40_225.0)          # straight to Q3
        assert rm.get_risk("YMU6").sl_price == 40_150.0
        update = rm.on_price_update("YMU6", 40_151.0)  # pullback, above stop
        assert update.new_stop is None
        assert update.reason == "none"
        assert rm.get_risk("YMU6").sl_price == 40_150.0

    def test_sl_hit_after_ratchet(self):
        rm = self._risk()
        rm.on_price_update("YMU6", 40_150.0)           # stop → 40,075
        assert rm.on_price_update("YMU6", 40_074.0).reason == "sl"

    def test_short_side_mirrors(self):
        rm = self._risk(side="sell")
        risk = rm.get_risk("YMU6")
        assert risk.sl_price == 40_100.0
        assert risk.tp_price == 39_700.0
        assert rm.on_price_update("YMU6", 39_925.0).new_stop == 40_000.0  # BE
        assert rm.on_price_update("YMU6", 39_850.0).new_stop == 39_925.0
        assert rm.on_price_update("YMU6", 39_700.0).reason == "tp"


class TestFuturesPosition:
    def test_long_pnl_in_tick_value(self):
        pt = PositionTracker(tick_size=1.0, tick_value=5.0)     # YM
        pt.on_fill("YMU6", "buy", 1, 40_000.0)
        pt.update_mark_price("YMU6", 40_075.0)
        assert pt.get_position("YMU6").unrealized_pnl == 375.0  # +$375 at Q1

    def test_short_open_and_profit(self):
        pt = PositionTracker(tick_size=0.25, tick_value=1.25)   # MES
        pt.on_fill("MESU6", "sell", 2, 6400.0)
        pos = pt.get_position("MESU6")
        assert pos.qty == -2
        pt.update_mark_price("MESU6", 6390.0)                   # 40 ticks favor
        assert pos.unrealized_pnl == 40 * 1.25 * 2

    def test_close_realizes(self):
        pt = PositionTracker(tick_size=1.0, tick_value=5.0)
        pt.on_fill("YMU6", "buy", 1, 40_000.0)
        pt.on_fill("YMU6", "sell", 1, 40_150.0, fee=2.5)
        pos = pt.get_position("YMU6")
        assert pos.qty == 0
        assert pos.realized_pnl == 750.0 - 2.5

    def test_flip_through_zero_sets_new_basis(self):
        pt = PositionTracker(tick_size=1.0, tick_value=5.0)
        pt.on_fill("YMU6", "buy", 1, 40_000.0)
        pt.on_fill("YMU6", "sell", 2, 40_100.0)     # close long, open short
        pos = pt.get_position("YMU6")
        assert pos.qty == -1
        assert pos.avg_price == 40_100.0
        assert pos.realized_pnl == 500.0


class TestOrderBook:
    def _book(self):
        book = OrderBook("YMU6", tick_size=1.0)
        book.apply_dom({
            "bids": [{"price": 40_000 - k, "size": 10 + k} for k in range(10)],
            "asks": [{"price": 40_001 + k, "size": 10} for k in range(10)],
        })
        return book

    def test_best_and_spread(self):
        book = self._book()
        assert book.best_bid()[0] == 40_000
        assert book.best_ask()[0] == 40_001
        assert book.spread_ticks() == 1.0
        assert book.mid_price() == 40_000.5

    def test_imbalance_sign(self):
        book = self._book()
        assert book.imbalance() > 0        # bids stacked deeper

    def test_desync_on_malformed(self):
        book = self._book()
        book.apply_dom({"bids": [{"prize": 1}], "asks": []})
        assert not book.synced
        assert book.best_bid() is None


class _FrozenSession:
    def __init__(self, open_=True, flatten=False):
        self.open_ = open_
        self.flatten = flatten

    def is_entry_allowed(self, now):
        return self.open_

    def should_flatten(self, now):
        return self.flatten


class _NoNews:
    def entering_blackout(self, prev, now):
        return None

    def active_blackout(self, now):
        return None


def _engine(session=None, news=None, **kwargs):
    engine = FuturesOrderFlowStrategy(
        product=YM,
        contract_symbol="YMU6",
        analyzer=OrderFlowAnalyzer(imbalance_threshold=0.1, min_confidence=0.5),
        price_action=None,                       # isolate layer-1 behaviour
        risk_manager=RiskManager(YM),
        position_tracker=PositionTracker(YM.tick_size, YM.tick_value),
        executor=DryRunExecutor("YM"),
        session_manager=session or _FrozenSession(),
        news_guard=news or _NoNews(),
        now_fn=lambda: datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc),
        **kwargs,
    )
    book = OrderBook("YMU6", YM.tick_size)
    engine.attach_orderbook(book)
    return engine


def _stacked_book(engine, bid_size=500, ask_size=5):
    engine.book.apply_dom({
        "bids": [{"price": 40_000 - k, "size": bid_size} for k in range(10)],
        "asks": [{"price": 40_001 + k, "size": ask_size} for k in range(10)],
    })


class TestStrategyGates:
    def test_strong_imbalance_enters_long_with_bracket(self):
        engine = _engine()
        _stacked_book(engine)
        asyncio.run(engine.on_book_update())
        entries = engine.executor.entries
        assert len(entries) == 1
        assert entries[0]["side"] == "buy"
        assert entries[0]["limit"] == 40_000.0
        assert entries[0]["stop"] == 39_900.0     # 100 ticks = $500 (§13)

    def test_sell_signal_opens_short(self):
        engine = _engine()
        _stacked_book(engine, bid_size=5, ask_size=500)
        asyncio.run(engine.on_book_update())
        assert engine.executor.entries[0]["side"] == "sell"
        assert engine.executor.entries[0]["stop"] == 40_101.0

    def test_closed_session_blocks_entry(self):
        engine = _engine(session=_FrozenSession(open_=False, flatten=True))
        _stacked_book(engine)
        asyncio.run(engine.on_book_update())
        assert engine.executor.entries == []
        assert engine.skips.get("F1_session") == 1

    def test_stale_contract_blocks_entry(self):
        engine = _engine(contract_fresh=lambda: False)
        _stacked_book(engine)
        asyncio.run(engine.on_book_update())
        assert engine.executor.entries == []
        assert engine.skips.get("F3_contract_stale") == 1

    def test_lifecycle_gate_blocks_entry(self):
        engine = _engine(lifecycle_ok=lambda: False)
        _stacked_book(engine)
        asyncio.run(engine.on_book_update())
        assert engine.executor.entries == []
        assert engine.skips.get("F4_lifecycle") == 1

    def test_wide_spread_blocks_entry(self):
        engine = _engine()
        engine.book.apply_dom({
            "bids": [{"price": 40_000, "size": 500}],
            "asks": [{"price": 40_005, "size": 5}],   # 5 ticks > max 2
        })
        asyncio.run(engine.on_book_update())
        assert engine.executor.entries == []
        assert engine.skips.get("G0_spread") == 1

    def test_no_pyramiding_while_in_position(self):
        engine = _engine()
        _stacked_book(engine)

        async def scenario():
            await engine.on_book_update()
            await engine.on_fill("buy", 1, 40_000.0)      # entry fills
            engine._last_order_time = 0                   # defeat cooldown
            await engine.on_book_update()                 # signal still BUY
        asyncio.run(scenario())
        assert len(engine.executor.entries) == 1
        assert engine.skips.get("in_position") == 1

    def test_fill_then_quadrant_stop_modification(self):
        engine = _engine()
        _stacked_book(engine)

        async def scenario():
            await engine.on_fill("buy", 1, 40_000.0)
            await engine.on_trade(40_075.0, 1, "buy")     # Q1 → BE stop modify
        asyncio.run(scenario())
        risk = engine.risk.get_risk("YMU6")
        assert risk.sl_price == 40_000.0


class TestSyntheticEndToEnd:
    def test_main_synthetic_runs_clean(self, tmp_path, monkeypatch):
        """Full pipeline through main.py's synthetic feed: config → db →
        lifecycle seed → engine → gates — no crash, gates exercised."""
        import main as main_mod
        db = Database(tmp_path / "bot.db")
        main_mod.seed_legacy_lifecycle(db, "YM")
        db.upsert_active_contract("YM", "YMU6", "SEP 2026", "2026-08-14", 1, 1)
        engine = main_mod.build_engine(CONFIG, db, "YM", "YMU6")
        engine.now_fn = lambda: datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc)
        asyncio.run(main_mod.run_synthetic(engine, ticks=500))
        assert sum(engine.skips.values()) > 0     # pipeline actually gated
