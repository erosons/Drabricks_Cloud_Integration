"""TrailRunner (live demo loop) — offline tests with a fake executor."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from src.config_loader import load_config
from src.trading.trail_runner import BarAggregator, TrailRunner

CONFIG = load_config(str(Path(__file__).parent.parent / "config"))
MES = CONFIG.products["MES"]
PARAMS = dict(CONFIG.strategies["momentum_dollar_trail"].params)


class _Session:
    def __init__(self):
        self.open_, self.flatten = True, False

    def is_entry_allowed(self, now):
        return self.open_

    def should_flatten(self, now):
        return self.flatten


class _Exec:
    def __init__(self):
        self.calls = []

    async def enter(self, symbol, side, qty, limit, stop):
        self.calls.append(("enter", side, limit, stop))
        return True

    async def modify_stop(self, symbol, new_stop):
        self.calls.append(("modify_stop", new_stop))

    async def flatten(self, symbol, reason):
        self.calls.append(("flatten", reason))

    async def cancel_working(self, symbol, reason):
        self.calls.append(("cancel", reason))


def _runner():
    r = TrailRunner(MES, "MESU6", PARAMS, _Session(),
                    now_fn=lambda: datetime(2026, 8, 24, 15, 0,
                                            tzinfo=timezone.utc))
    r.executor = _Exec()
    return r


def _feed_bars(runner, closes, start_min=0):
    """Feed one trade per minute so each new trade closes the prior bar."""
    async def go():
        for i, c in enumerate(closes):
            await runner.on_trade(c, 1, "buy",
                                  ts_ns=(start_min + i) * 60_000_000_000)
    asyncio.run(go())


class TestBarAggregator:
    def test_bar_closes_on_minute_rollover(self):
        agg = BarAggregator()
        assert agg.on_trade(0, 100.0) is None
        assert agg.on_trade(30_000_000_000, 101.0) is None   # same minute
        closed = agg.on_trade(60_000_000_000, 102.0)
        assert closed.open == 100.0 and closed.high == 101.0 \
            and closed.close == 101.0


class TestTrailRunner:
    def test_two_up_closes_send_marketable_entry_with_bracket(self):
        r = _runner()
        _feed_bars(r, [6400.0, 6400.25, 6400.75, 6401.0])
        # bars closed: 6400.0, 6400.25(+1t), 6400.75(+2t) → signal on 3rd
        enters = [c for c in r.executor.calls if c[0] == "enter"]
        assert enters == [("enter", "buy", 6400.75 + 0.50, 6400.75 - 20.0)]

    def test_trail_ratchets_after_fill_never_loosens(self):
        r = _runner()
        asyncio.run(r.on_fill("buy", 1, 6401.0))
        _feed_bars(r, [6410.0, 6440.0, 6430.0, 6431.0])
        mods = [c[1] for c in r.executor.calls if c[0] == "modify_stop"]
        assert mods == [6390.0, 6420.0]      # 6410−20 then 6440−20; no loosen

    def test_session_flatten_flattens_open_position(self):
        r = _runner()
        asyncio.run(r.on_fill("buy", 1, 6401.0))
        r.session.flatten = True
        _feed_bars(r, [6402.0, 6402.5])
        kinds = [c[0] for c in r.executor.calls]
        assert "cancel" in kinds and "flatten" in kinds

    def test_no_entries_when_session_closed(self):
        r = _runner()
        r.session.open_ = False
        _feed_bars(r, [6400.0, 6400.25, 6400.75, 6401.0, 6401.5])
        assert [c for c in r.executor.calls if c[0] == "enter"] == []

    def test_fill_roundtrip_resets_state(self):
        r = _runner()
        asyncio.run(r.on_fill("buy", 1, 6401.0))
        assert r.pos == 1 and r.extreme == 6401.0
        asyncio.run(r.on_fill("sell", 1, 6395.0))
        assert r.pos == 0 and r.extreme is None and r.last_stop is None

    def test_init_dist_is_pure_trail_at_frozen_config(self):
        r = _runner()
        assert r.trail == 20.0 and r.init_dist == 20.0   # merged config
