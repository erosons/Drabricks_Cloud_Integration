"""Bar simulator + indicator + card-strategy tests (all offline)."""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.config_loader import load_config
from src.research import indicators as ind
from src.research.bar_backtester import BarBracketSim, Entry
from src.research.bars import add_session_columns
from src.research.card_strategies import ALL_STRATEGIES, SupertrendRsi

CONFIG = load_config(str(Path(__file__).parent.parent / "config"))
MES = CONFIG.products["MES"]
SESSION = CONFIG.raw["session"]


def _bars(rows, start="2026-03-04 15:00", freq="5min"):
    """rows = list of (open, high, low, close[, volume]) — in-session ET."""
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    df = pd.DataFrame([r if len(r) == 5 else (*r, 100) for r in rows],
                      columns=["open", "high", "low", "close", "volume"],
                      index=idx)
    df.index.name = "ts"
    df["buy_volume"] = df["volume"] / 2
    df["sell_volume"] = df["volume"] / 2
    return add_session_columns(df, SESSION)


class _OneShot:
    """Strategy stub: emits one fixed Entry on the requested bar."""
    name, timeframe_min, notes = "stub", 5, ""

    def __init__(self, entry, at=0):
        self.entry, self.at = entry, at
        self.managed = []

    def prepare(self, df):
        return df

    def on_bar(self, df, i):
        return self.entry if i == self.at else None

    def manage(self, df, i, pos):
        self.managed.append(i)
        return None


def _sim(rows, entry, at=0, **kw):
    strat = _OneShot(entry, at)
    df = _bars(rows)
    return BarBracketSim(strat, MES, df, **kw).run()


class TestBarFills:
    def test_stop_entry_needs_penetration_not_touch(self):
        entry = Entry("buy", "stop", 6401.00, stop=6395.00)
        res = _sim([(6400, 6400.5, 6399, 6400),
                    (6400, 6401.0, 6399, 6400),     # touch only
                    (6400, 6400.5, 6399, 6400)], entry)
        assert res.trades == [] and res.flags["entries"] == 0

    def test_stop_entry_fills_with_slippage(self):
        entry = Entry("buy", "stop", 6401.00, stop=6395.00, target=6420.00)
        res = _sim([(6400, 6400.5, 6399, 6400),
                    (6400, 6402.0, 6399, 6401.5),   # through
                    (6401, 6402.0, 6400, 6401)], entry)
        assert res.flags["entries"] == 1
        assert res.trades[0].entry_price == 6401.00 + 0.50   # +2 ticks

    def test_limit_entry_penetration_only(self):
        entry = Entry("buy", "limit", 6399.00, stop=6395.00)
        res = _sim([(6400, 6401, 6399.00, 6400),    # touch — no fill
                    (6400, 6401, 6398.75, 6400),    # through — fills at limit
                    (6400, 6401, 6399.5, 6400)], entry)
        assert res.flags["entries"] == 1
        assert res.trades[0].entry_price == 6399.00

    def test_protective_stop_first_when_both_hit(self):
        entry = Entry("buy", "market", None, stop=6395.00, target=6405.00)
        res = _sim([(6400, 6401, 6399, 6400),
                    (6400, 6406, 6394, 6400),       # both stop and target
                    (6400, 6401, 6399, 6400)], entry)
        t = res.trades[0]
        assert t.exit_reason == "stop"
        assert t.exit_price == 6395.00 - 0.50        # stop − slippage
        assert res.flags["stop_and_target_same_bar"] == 1

    def test_target_fills_at_limit_no_improvement(self):
        entry = Entry("buy", "market", None, stop=6390.00, target=6405.00)
        res = _sim([(6400, 6401, 6399, 6400),
                    (6400, 6401, 6399, 6400),
                    (6404, 6410, 6403, 6409)], entry)
        assert res.trades[0].exit_reason == "target"
        assert res.trades[0].exit_price == 6405.00

    def test_market_entry_next_open_with_slippage(self):
        entry = Entry("buy", "market", None, stop=6398.00)
        res = _sim([(6400, 6401, 6399, 6400),
                    (6402, 6403, 6401, 6402),
                    (6402, 6403, 6401, 6402)], entry)
        assert res.trades[0].entry_price == 6402 + 0.50

    def test_session_flatten_closes_position(self):
        entry = Entry("buy", "market", None, stop=6395.00)
        rows = [(6400, 6401, 6399, 6400)] * 12
        strat = _OneShot(entry, 0)
        df = _bars(rows, start="2026-03-04 20:10")   # 15:10 ET → hits 15:55
        res = BarBracketSim(strat, MES, df).run()
        assert res.trades[0].exit_reason == "session_flatten"

    def test_time_stop_exits_next_open(self):
        entry = Entry("buy", "market", None, stop=6395.00, time_stop_bars=2)
        res = _sim([(6400, 6401, 6399, 6400)] * 6, entry)
        assert res.trades[0].exit_reason == "time_stop"

    def test_wide_stop_skipped_by_risk_guard(self):
        entry = Entry("buy", "market", None, stop=6200.00)  # $1000 risk
        res = _sim([(6400, 6401, 6399, 6400)] * 3, entry)
        assert res.trades == []
        assert res.flags["skipped_wide_stop"] == 1

    def test_trail_ratchets_never_loosens(self):
        class Trailing(_OneShot):
            def manage(self, df, i, pos):
                return 6399.0 if i == 1 else 6397.0   # tighten then loosen
        strat = Trailing(Entry("buy", "market", None, stop=6395.00), 0)
        df = _bars([(6400, 6401, 6399.25, 6400)] * 3
                   + [(6400, 6401, 6398.0, 6400)])    # hits 6399, not 6397
        res = BarBracketSim(strat, MES, df).run()
        assert res.trades[0].exit_reason == "stop"
        assert res.trades[0].exit_price == 6399.0 - 0.50


class TestIndicators:
    def test_rsi_bounds_and_direction(self):
        up = pd.Series(np.linspace(100, 200, 60))
        r = ind.rsi(up)
        assert 50 < r.iloc[-1] <= 100

    def test_supertrend_direction_follows_trend(self):
        n = 80
        close = np.concatenate([np.linspace(100, 130, 40),
                                np.linspace(130, 100, 40)])
        df = pd.DataFrame({"open": close, "high": close + 1,
                           "low": close - 1, "close": close})
        st = ind.supertrend(df)
        assert st["st_dir"].iloc[35] == 1
        assert st["st_dir"].iloc[-1] == -1

    def test_fractals_have_no_lookahead(self):
        rng = np.random.default_rng(7)
        close = 100 + rng.normal(0, 1, 60).cumsum()
        df = pd.DataFrame({"open": close, "high": close + 0.5,
                           "low": close - 0.5, "close": close})
        full = ind.fractals(df)
        trunc = ind.fractals(df.iloc[:40])
        # values at bar 37 must agree whether or not the future exists
        a, b = full["fractal_up"].iloc[37], trunc["fractal_up"].iloc[37]
        assert (np.isnan(a) and np.isnan(b)) or a == b

    def test_session_vwap_resets_daily(self):
        df = _bars([(6400, 6401, 6399, 6400)] * 4, freq="1min")
        df2 = _bars([(6500, 6501, 6499, 6500)] * 4,
                    start="2026-03-05 15:00", freq="1min")
        both = pd.concat([df, df2])
        v = ind.session_vwap(both)
        assert abs(v["vwap"].iloc[3] - 6400) < 1
        assert abs(v["vwap"].iloc[-1] - 6500) < 1


class TestCardStrategies:
    def test_all_cards_have_config_params(self):
        for name in ALL_STRATEGIES:
            assert name in CONFIG.strategies, name

    def test_supertrend_rsi_enters_on_flip(self):
        dn = [(6400 - 0.25 * k, 6401 - 0.25 * k, 6399 - 0.25 * k,
               6400 - 0.25 * k) for k in range(30)]
        base = 6400 - 0.25 * 29
        up = [(base + 2 * k, base + 2 * k + 1, base + 2 * k - 1,
               base + 2 * k) for k in range(30)]
        rows = dn + up
        df = _bars(rows, start="2026-03-02 15:00", freq="30min")
        strat = SupertrendRsi(CONFIG.strategies["supertrend_rsi"].params, MES)
        df = strat.prepare(df)
        entries = [strat.on_bar(df, i) for i in range(len(df))]
        longs = [e for e in entries if e and e.side == "buy"]
        assert longs, "uptrend flip with RSI>60 must produce a long"

    def test_every_strategy_runs_clean_on_random_walk(self):
        rng = np.random.default_rng(42)
        n = 400
        close = 6400 + np.round(rng.normal(0, 2, n).cumsum() * 4) / 4
        rows = [(close[k], close[k] + 1, close[k] - 1, close[k],
                 int(rng.integers(50, 500))) for k in range(n)]
        for name, cls in ALL_STRATEGIES.items():
            strat = cls(CONFIG.strategies[name].params, MES)
            df = _bars(rows, start="2026-03-02 15:00",
                       freq=f"{strat.timeframe_min}min")
            df = strat.prepare(df)
            res = BarBracketSim(strat, MES, df).run()   # must not raise
            assert res.bars == n, name
