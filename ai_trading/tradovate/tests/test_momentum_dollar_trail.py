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

    def test_loss_capped_at_hundred_dollars(self):
        # frozen config: min(trail $20, $100/$5-per-pt = 20 pts) = 20 pts
        rows = [(6400, 6400.5, 6399.5, 6400),
                (6400, 6400.5, 6399.5, 6400.25),
                (6400.25, 6400.75, 6400, 6400.5),
                (6400.5, 6400.75, 6400.25, 6400.5),   # entry bar (market)
                (6400.5, 6400.5, 6378.0, 6379.0)]     # crash through stop
        res = _run(rows)
        t = res.trades[0]
        assert t.exit_reason == "stop"
        # signal-close stop 6380.5 is ratcheted to fill−20 = 6381 by the
        # first manage() call; exit = 6381 − 2 ticks slip = 6380.5
        assert abs(t.exit_price - 6380.5) < 1e-9
        # ≈ $100 intended risk + slippage both ways + fees
        assert -108.0 < t.pnl_usd < -102.0

    def test_pure_trail_ratchets_from_extreme(self):
        # entry ~6401; run to 6440 → trail = 6420; dip $21 hits it
        rows = [(6400, 6400.5, 6399.5, 6400),
                (6400, 6400.5, 6399.5, 6400.25),
                (6400.25, 6400.75, 6400, 6400.5),
                (6400.5, 6401, 6400.25, 6401),        # entry bar
                (6401, 6440, 6400.75, 6439),          # run — trail to 6420
                (6439, 6439, 6418.0, 6419.0)]         # dip $21 → stop 6420
        res = _run(rows)
        t = res.trades[0]
        assert t.exit_reason == "stop"
        assert t.pnl_usd > 0                          # trailed into profit
        assert abs(t.exit_price - (6440 - 20.00 - 0.50)) < 1e-9

    def test_reenters_after_stop_when_movement_persists(self):
        up = [(6400 + 0.5 * k, 6400.75 + 0.5 * k, 6399.75 + 0.5 * k,
               6400.5 + 0.5 * k) for k in range(4)]
        crash = [(6402.5, 6402.5, 6376.0, 6377.0)]    # through the 20-pt stop
        up2 = [(6377 + 0.5 * k, 6377.75 + 0.5 * k, 6376.75 + 0.5 * k,
                6377.5 + 0.5 * k) for k in range(5)]
        res = _run(up + crash + up2)
        assert res.flags["entries"] >= 2
