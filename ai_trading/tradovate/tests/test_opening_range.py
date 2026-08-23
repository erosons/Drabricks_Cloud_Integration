"""OpeningRange card tests: range math, news rule, one-and-done, filters."""

import asyncio
from pathlib import Path

import numpy as np
import pandas as pd

from src.config_loader import load_config
from src.research.bar_backtester import BarBracketSim
from src.research.bars import add_session_columns
from src.research.card_strategies import OpeningRange

CONFIG = load_config(str(Path(__file__).parent.parent / "config"))
MES = CONFIG.products["MES"]
PARAMS = dict(CONFIG.strategies["opening_range"].params)


def _day(rows, day="2026-03-04"):
    """rows of (o,h,l,c) as 5m bars starting at RTH open 08:00 ET (13:00 UTC
    in March/EST)."""
    idx = pd.date_range(f"{day} 13:00", periods=len(rows), freq="5min",
                        tz="UTC")
    df = pd.DataFrame([(*r, 100) for r in rows],
                      columns=["open", "high", "low", "close", "volume"],
                      index=idx)
    df["buy_volume"] = 50
    df["sell_volume"] = 50
    df.index.name = "ts"
    return add_session_columns(df, CONFIG.raw["session"])


def _quiet(n, px=6400.0, rng=1.0):
    return [(px, px + rng, px - rng, px)] * n


def _strategy(**over):
    # behaviour tests relax the quality floor (flat fixtures make OR range
    # ~= ATR by construction); the filter has its own dedicated test
    return OpeningRange({**PARAMS, "min_range_atr": 0.5, **over}, MES)


def _entries(df, strat):
    df = strat.prepare(df)
    out = []
    for i in range(len(df)):
        e = strat.on_bar(df, i)
        if e:
            out.append((i, e))
    return out


class TestOpeningRange:
    def test_range_break_goes_long_after_news_window(self):
        # 30m window = bars 0-5; quiet range then breakout close at bar 10
        rows = _quiet(10) + [(6400, 6404, 6400, 6403.5)] + _quiet(5)
        entries = _entries(_day(rows), _strategy())
        assert len(entries) == 1
        i, e = entries[0]
        assert i == 10 and e.side == "buy"
        assert e.stop == 6400.0                 # mid of 6399-6401 range
        # 08:45 news rule: bar 10 = minute 50 ≥ 45 ✓ (never earlier)
        assert i * 5 >= 45

    def test_no_entry_before_0845_even_if_broken(self):
        # breakout close at bar 7 (minute 35) — window done, but before 08:45
        rows = _quiet(7) + [(6400, 6404, 6400, 6403.5)] + _quiet(2) \
            + [(6400, 6404, 6400, 6403.5)] + _quiet(4)
        entries = _entries(_day(rows), _strategy())
        assert entries and entries[0][0] == 10   # fires at min 50, not 35

    def test_short_side_mirror(self):
        rows = _quiet(10) + [(6400, 6400, 6396, 6396.5)] + _quiet(4)
        entries = _entries(_day(rows), _strategy())
        assert entries[0][1].side == "sell"
        assert entries[0][1].stop == 6400.0

    def test_one_and_done_per_session(self):
        rows = (_quiet(10) + [(6400, 6404, 6400, 6403.5)]
                + [(6400, 6404, 6396, 6396.0)] + _quiet(10))
        entries = _entries(_day(rows), _strategy())
        assert len(entries) == 1

    def test_entry_cutoff_expires(self):
        rows = _quiet(30) + [(6400, 6404, 6400, 6403.5)] + _quiet(2)
        # breakout at bar 30 = minute 150 ≥ cutoff 120 → no entry
        assert _entries(_day(rows), _strategy(entry_cutoff_min=120)) == []

    def test_dead_open_skipped_by_quality_filter(self):
        # prior session sets ATR context ~2; next open's range is 0.25 —
        # far below 1.0×ATR → session skipped even on a later breakout
        prior = _day(_quiet(30, rng=2.0), "2026-03-03")
        tiny = [(6400, 6400.25, 6400, 6400.1)] * 6
        rows = tiny + _quiet(4) + [(6400, 6406, 6400, 6405)] + _quiet(4)
        df = pd.concat([prior, _day(rows, "2026-03-04")])
        strat = OpeningRange(dict(PARAMS), MES)   # real 1.0 floor
        prepared = strat.prepare(df)
        entries = [strat.on_bar(prepared, i) for i in range(len(prepared))]
        assert [e for e in entries if e] == []

    def test_opposite_stop_mode(self):
        rows = _quiet(10) + [(6400, 6404, 6400, 6403.5)] + _quiet(4)
        entries = _entries(_day(rows), _strategy(stop_mode="opposite"))
        assert entries[0][1].stop == 6399.0     # far side of range

    def test_full_sim_two_days_end_to_end(self):
        d1 = _day(_quiet(10) + [(6400, 6404, 6400, 6403.5)]
                  + [(6404, 6412, 6403, 6411)] + _quiet(8), "2026-03-04")
        d2 = _day(_quiet(20), "2026-03-05")
        df = pd.concat([d1, d2])
        strat = _strategy()
        res = BarBracketSim(strat, MES, strat.prepare(df)).run()
        assert len(res.trades) == 1
        assert res.trades[0].exit_reason == "target"   # 2R = +7 pts from 6403.5+slip
