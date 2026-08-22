"""Backtester tests: pessimistic fill model, replay loop, stats, DB row."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from src.config_loader import load_config
from src.research.backtester import (
    Backtester,
    BacktestResult,
    PessimisticBracketExecutor,
    SimTrade,
    Tick,
)
from src.storage.db import Database

CONFIG = load_config(str(Path(__file__).parent.parent / "config"))
MES = CONFIG.products["MES"]

NOW = datetime(2026, 3, 4, 15, 0, tzinfo=timezone.utc)  # 10:00 ET, in session


def _tick(price, bid=None, ask=None, side="sell", ts_ns=None, size=1):
    bid = bid if bid is not None else price - 0.25
    ask = ask if ask is not None else price + 0.25
    ts = ts_ns if ts_ns is not None else int(NOW.timestamp() * 1e9)
    return Tick(ts, price, size, side, bid, ask, 10, 10)


class _Fills:
    def __init__(self):
        self.fills = []

    async def __call__(self, side, qty, price, fee):
        self.fills.append((side, qty, price, fee))


def _executor(slippage_ticks=2, commission=1.10):
    fills = _Fills()
    ex = PessimisticBracketExecutor(MES, fills, slippage_ticks, commission)
    return ex, fills


def _run(coro):
    return asyncio.run(coro)


class TestPessimisticFills:
    def test_touch_is_never_a_fill(self):
        ex, fills = _executor()
        _run(ex.enter("S", "buy", 1, 6400.00, 6390.00))
        _run(ex.on_tick(_tick(6400.00), NOW))          # touch
        assert fills.fills == []
        assert ex.flags["touch_no_fill"] == 1
        assert ex.entry is not None                    # still resting

    def test_penetration_fills_at_limit(self):
        ex, fills = _executor()
        _run(ex.enter("S", "buy", 1, 6400.00, 6390.00))
        _run(ex.on_tick(_tick(6399.75), NOW))          # traded through
        assert fills.fills == [("buy", 1, 6400.00, 1.10)]
        assert ex.pos_qty == 1
        assert ex.stop == {"price": 6390.00}           # OSO armed

    def test_sell_entry_penetration(self):
        ex, fills = _executor()
        _run(ex.enter("S", "sell", 1, 6400.00, 6410.00))
        _run(ex.on_tick(_tick(6400.25), NOW))
        assert fills.fills[0][:3] == ("sell", 1, 6400.00)
        assert ex.pos_qty == -1

    def test_long_stop_fills_with_slippage_against(self):
        ex, fills = _executor(slippage_ticks=2)
        _run(ex.enter("S", "buy", 1, 6400.00, 6390.00))
        _run(ex.on_tick(_tick(6399.75), NOW))
        _run(ex.on_tick(_tick(6389.75), NOW))          # gapped through stop
        # worse of (stop, trade) − 2 ticks = 6389.75 − 0.50
        assert fills.fills[-1][:3] == ("sell", 1, 6389.25)
        assert ex.pos_qty == 0
        assert ex.trades[0].exit_reason == "stop"
        assert ex.trades[0].pnl_usd < 0

    def test_short_stop_symmetric(self):
        ex, fills = _executor(slippage_ticks=2)
        _run(ex.enter("S", "sell", 1, 6400.00, 6410.00))
        _run(ex.on_tick(_tick(6400.25), NOW))
        _run(ex.on_tick(_tick(6410.50), NOW))
        assert fills.fills[-1][:3] == ("buy", 1, 6411.00)   # 6410.50 + 0.50

    def test_flatten_fills_next_tick_with_adverse_slippage(self):
        ex, fills = _executor(slippage_ticks=2)
        _run(ex.enter("S", "buy", 1, 6400.00, 6390.00))
        _run(ex.on_tick(_tick(6399.75), NOW))
        _run(ex.flatten("S", "tp"))
        assert len(fills.fills) == 1                   # nothing yet
        _run(ex.on_tick(_tick(6412.00), NOW))
        assert fills.fills[-1][:3] == ("sell", 1, 6411.50)  # −2 ticks
        t = ex.trades[0]
        assert t.exit_reason == "tp" and t.pnl_usd > 0
        # (6411.50 − 6400) × $5/pt − 2 × $1.10
        assert abs(t.pnl_usd - (11.50 * 5.0 - 2.20)) < 1e-9

    def test_one_bracket_guard_refuses_second_entry(self):
        ex, _ = _executor()
        assert _run(ex.enter("S", "buy", 1, 6400.00, 6390.00)) is True
        assert _run(ex.enter("S", "buy", 1, 6401.00, 6391.00)) is False
        assert ex.flags["entries_refused_busy"] == 1

    def test_cancel_working_keeps_stop(self):
        ex, _ = _executor()
        _run(ex.enter("S", "buy", 1, 6400.00, 6390.00))
        _run(ex.on_tick(_tick(6399.75), NOW))          # filled, stop armed
        _run(ex.cancel_working("S", "blackout"))
        assert ex.stop is not None                     # protective stop survives
        _run(ex.enter("S", "buy", 1, 6400.00, 6390.00))
        _run(ex.cancel_working("S", "blackout"))
        assert ex.pos_qty == 1                         # in-position unchanged

    def test_force_close_flags_and_fills(self):
        ex, fills = _executor(slippage_ticks=2)
        _run(ex.enter("S", "buy", 1, 6400.00, 6390.00))
        _run(ex.on_tick(_tick(6399.75), NOW))
        _run(ex.force_close(6405.00, "end_of_data"))
        assert ex.pos_qty == 0
        assert ex.trades[0].exit_reason == "end_of_data"
        assert fills.fills[-1][:3] == ("sell", 1, 6404.50)


class TestStats:
    def _result(self, pnls):
        trades = [SimTrade(side="buy", qty=1, entry_ts="t", entry_price=0,
                           exit_ts="t", exit_price=0, exit_reason="tp",
                           fees=2.20, pnl_usd=p) for p in pnls]
        return BacktestResult(product="MES", date_from="a", date_to="b",
                              ticks=0, trades=trades, skips={}, fill_flags={})

    def test_win_rate_and_net(self):
        s = self._result([10, -5, 20, -5]).stats()
        assert s["trades"] == 4 and s["wins"] == 2 and s["losses"] == 2
        assert s["win_rate"] == 0.5
        assert abs(s["net_profit"] - 20.0) < 1e-9

    def test_max_drawdown_peak_to_trough(self):
        s = self._result([10, -15, -10, 30]).stats()
        assert abs(s["max_drawdown"] - 25.0) < 1e-9    # peak 10 → trough −15
        assert s["largest_loss"] == -15

    def test_profit_factor(self):
        s = self._result([30, -10]).stats()
        assert abs(s["profit_factor"] - 3.0) < 1e-9

    def test_persist_writes_backtest_runs_row(self, tmp_path):
        db = Database(tmp_path / "t.db")
        run_id = self._result([10, -5]).persist(db)
        row = db.conn.execute("SELECT * FROM backtest_runs WHERE id=?",
                              (run_id,)).fetchone()
        assert row["strategy"] == "order_flow_scalp"
        assert row["kind"] == "limited"
        assert row["trades"] == 2
        assert abs(row["net_profit"] - 5.0) < 1e-9


class TestReplayEndToEnd:
    def _ticks(self, n=400, price=6400.0, ts0=NOW):
        """Session-hours ticks with a heavy bid book and buy tape — enough
        signal for the engine to go long; then a rally so TP path exercises."""
        ts = int(ts0.timestamp() * 1e9)
        out = []
        for i in range(n):
            p = price + (0.25 * (i // 40))             # slow grind up
            out.append(Tick(ts + i * 200_000_000, p, 5, "buy",
                            p - 0.25, p, 400, 5))
        return out

    def test_replay_runs_and_reports(self):
        bt = Backtester(CONFIG, "MES")
        result = asyncio.run(bt.run(iter(self._ticks()), progress_every=0))
        assert result.ticks == 400
        assert result.fill_flags["news_guard"].startswith("PERMISSIVE")
        # engine saw session-open ticks: no F1 skips at 10:00 ET Wednesday
        assert "F1_session" not in result.skips

    def test_out_of_session_ticks_are_gated(self):
        night = datetime(2026, 3, 4, 3, 0, tzinfo=timezone.utc)  # 22:00 ET Tue
        bt = Backtester(CONFIG, "MES")
        result = asyncio.run(bt.run(iter(self._ticks(ts0=night)),
                                    progress_every=0))
        assert result.skips.get("F1_session") == 400
        assert result.trades == []

    def test_cooldown_runs_on_sim_time(self):
        bt = Backtester(CONFIG, "MES")
        asyncio.run(bt.run(iter(self._ticks(n=5)), progress_every=0))
        # clock_fn reflects the LAST tick's sim time, not the wall clock
        assert abs(bt.engine.clock_fn() -
                   (NOW.timestamp() + 4 * 0.2)) < 1e-6
