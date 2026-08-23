"""momentum_dollar_trail: trigger, $1 trail ratchet, $5 loss cap."""

from pathlib import Path

import pandas as pd

from src.config_loader import load_config
from src.research.bar_backtester import BarBracketSim
from src.research.bars import add_session_columns
from src.research.card_strategies import MomentumDollarTrail

CONFIG = load_config(str(Path(__file__).parent.parent / "config"))
MES = CONFIG.products["MES"]


def _bars(rows, start="2026-03-04 15:00"):
    idx = pd.date_range(start, periods=len(rows), freq="1min", tz="UTC")
    df = pd.DataFrame([(*r, 100) for r in rows],
                      columns=["open", "high", "low", "close", "volume"],
                      index=idx)
    df["buy_volume"] = 50
    df["sell_volume"] = 50
    df.index.name = "ts"
    return add_session_columns(df, CONFIG.raw["session"])


def _run(rows):
    strat = MomentumDollarTrail(
        CONFIG.strategies["momentum_dollar_trail"].params, MES)
    df = _bars(rows)
    return BarBracketSim(strat, MES, strat.prepare(df)).run()


class TestMomentumDollarTrail:
    def test_two_up_closes_enter_long(self):
        rows = [(6400, 6400.5, 6399.5, 6400),
                (6400, 6400.5, 6399.5, 6400.25),   # +1 tick
                (6400.25, 6400.75, 6400, 6400.5),  # +1 tick → trigger
                (6400.5, 6401, 6400.25, 6400.75),
                (6400.75, 6401, 6400.5, 6400.75)]
        res = _run(rows)
        assert res.flags["entries"] == 1
        assert res.trades == [] or res.trades[0].side == "buy"

    def test_loss_capped_at_twenty_dollars(self):
        # v3: initial stop = min(trail $10, $20/$5-per-pt = 4 pts) = 4 pts
        rows = [(6400, 6400.5, 6399.5, 6400),
                (6400, 6400.5, 6399.5, 6400.25),
                (6400.25, 6400.75, 6400, 6400.5),
                (6400.5, 6400.75, 6400.25, 6400.5),   # entry bar (market)
                (6400.5, 6400.5, 6392.0, 6393.0)]     # crash through stop
        res = _run(rows)
        t = res.trades[0]
        assert t.exit_reason == "stop"
        # stop anchors at the SIGNAL close (6400.5) − 4 pts = 6396.5;
        # exit = stop − 2 ticks slip = 6396.0
        assert abs(t.exit_price - 6396.0) < 1e-9
        # ≈ $20 intended risk + $2.50 entry slip + $2.50 stop slip + $2.20 fees
        assert -28.0 < t.pnl_usd < -25.0

    def test_trail_takes_over_after_four_points(self):
        # entry ~6401; run to 6420 → trail = 6410 > initial 6395; dip hits it
        rows = [(6400, 6400.5, 6399.5, 6400),
                (6400, 6400.5, 6399.5, 6400.25),
                (6400.25, 6400.75, 6400, 6400.5),
                (6400.5, 6401, 6400.25, 6401),        # entry bar
                (6401, 6420, 6400.75, 6419),          # run — trail to 6410
                (6419, 6419, 6408.0, 6409.0)]         # dip $11 → stop 6410
        res = _run(rows)
        t = res.trades[0]
        assert t.exit_reason == "stop"
        assert t.pnl_usd > 0                          # trailed into profit
        assert abs(t.exit_price - (6420 - 10.00 - 0.50)) < 1e-9

    def test_reenters_after_stop_when_movement_persists(self):
        up = [(6400 + 0.5 * k, 6400.75 + 0.5 * k, 6399.75 + 0.5 * k,
               6400.5 + 0.5 * k) for k in range(4)]
        crash = [(6402.5, 6402.5, 6394.0, 6395.0)]    # through the 6-pt stop
        up2 = [(6395 + 0.5 * k, 6395.75 + 0.5 * k, 6394.75 + 0.5 * k,
                6395.5 + 0.5 * k) for k in range(5)]
        res = _run(up + crash + up2)
        assert res.flags["entries"] >= 2
