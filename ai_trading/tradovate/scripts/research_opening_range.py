"""opening_range: full research pipeline (card → holdout), spec discipline.

Stages run IN ORDER; the first FAIL stops the pipeline and the holdout
stays sealed. The holdout (B5) runs only if B1-B4 all pass — it was
pre-authorized by the user (2026-08-23) conditional on that.

  B1  robustness grid (450 cells × MES,MNQ), verdict per the recorded
      precedent: plateau clause ≥60% of ±1-step cells positive on BOTH
      products; the 2× clause is ONE-DIRECTIONAL (fails only if the
      baseline towers over its neighbors — b1_ruling, 2026-08-22)
  B_med frozen going-forward config = plateau MEDIAN cell (never best)
  B2  distribution sanity (hour ≤40%, news <25%, month ≤50%,
      net>0 without best trade, monthly sign agreement ≥6)
  B3  cost stress: net>0 on both products under slippage×2 AND comm×1.5
  B4  walk-forward: tune 3 months (±1-step cells, best expectancy,
      ≥8 trades else median), trade next month; 6 folds;
      PASS: aggregate OOS>0 both products, ≥4/6 folds non-negative,
      no fold loses >2× the average winning fold
  B5  holdout, ONE SHOT: B_med frozen, MC 90% expectancy band from
      bootstrapped dev trades RECORDED BEFORE the run; PASS iff holdout
      expectancy per trade falls inside the band on both products.

Every stage persists to research_results (phases or_*).
"""

from __future__ import annotations

import itertools
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config_loader import load_config
from src.research.bar_backtester import BarBracketSim
from src.research.bars import add_session_columns, load_bars
from src.research.card_strategies import OpeningRange
from src.storage.db import Database
from src.utils.logger import get_logger

log = get_logger("or_pipeline")

GRID = {
    "or_window_minutes": [15, 30, 45],
    "buffer_atr": [0.0, 0.05, 0.10, 0.15, 0.20],
    "stop_mode": ["mid", "opposite"],
    "target_rr": [1.5, 1.75, 2.0, 2.5, 3.0],
    "entry_cutoff_min": [90, 120, 150],
}
BASELINE = {"or_window_minutes": 30, "buffer_atr": 0.10, "stop_mode": "mid",
            "target_rr": 2.0, "entry_cutoff_min": 120}
NAMES = list(GRID)
PRODUCTS = ("MES", "MNQ")
DEV_TO = "2026-05-19"
HOLDOUT_FROM, HOLDOUT_TO = "2026-05-20", "2026-08-19"
ET = ZoneInfo("America/New_York")
FOLDS = [("2025-09-01", "2025-11-30", "2025-12-01", "2025-12-31"),
         ("2025-10-01", "2025-12-31", "2026-01-01", "2026-01-31"),
         ("2025-11-01", "2026-01-31", "2026-02-01", "2026-02-28"),
         ("2025-12-01", "2026-02-28", "2026-03-01", "2026-03-31"),
         ("2026-01-01", "2026-03-31", "2026-04-01", "2026-04-30"),
         ("2026-02-01", "2026-04-30", "2026-05-01", "2026-05-19")]

config = load_config(str(ROOT / "config"))
db = Database(ROOT / config.raw["database"]["path"])
_bars_cache: dict = {}


def bars(product: str, date_from=None, date_to=DEV_TO):
    key = (product, date_from, date_to)
    if key not in _bars_cache:
        df = load_bars(product, 5, ROOT / "data" / "databento",
                       date_from, date_to)
        _bars_cache[key] = add_session_columns(df, config.raw["session"])
    return _bars_cache[key]


def run_cell(product, cell, df, slippage=2, commission=1.10):
    params = {**config.strategies["opening_range"].params, **cell}
    strat = OpeningRange(params, config.products[product])
    return BarBracketSim(strat, config.products[product],
                         strat.prepare(df.copy()),
                         slippage_ticks=slippage,
                         commission_per_side=commission).run()


def record(phase, product, detail, notes, stats=None):
    s = stats or {}
    db.conn.execute(
        "INSERT INTO research_results (strategy, product, phase,"
        " timeframe_min, date_from, date_to, trades, wins, losses, win_rate,"
        " net_profit, fees, profit_factor, max_drawdown, largest_loss,"
        " flags_json, notes, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("opening_range", product, phase, 5, s.get("date_from"),
         s.get("date_to"), s.get("trades", 0), s.get("wins", 0),
         s.get("losses", 0), s.get("win_rate", 0.0),
         s.get("net_profit", 0.0), s.get("fees", 0.0),
         min(s.get("profit_factor", 0.0), 999.0),
         s.get("max_drawdown", 0.0), s.get("largest_loss", 0.0),
         json.dumps(detail), notes,
         datetime.now(timezone.utc).isoformat()))
    db.conn.commit()


def idx(k, v):
    return GRID[k].index(v)


def one_step_cells():
    ranges = []
    for k in NAMES:
        j = idx(k, BASELINE[k])
        ranges.append([GRID[k][x] for x in range(max(0, j - 1),
                                                 min(len(GRID[k]), j + 2))])
    return [dict(zip(NAMES, vals)) for vals in itertools.product(*ranges)]


def full_cells():
    return [dict(zip(NAMES, vals))
            for vals in itertools.product(*[GRID[k] for k in NAMES])]


def expectancy(s):
    return s["net_profit"] / s["trades"] if s["trades"] else 0.0


# ---------------------------------------------------------------- B1

def stage_b1():
    cells = full_cells()
    log.info("B1: %d cells × %d products", len(cells), len(PRODUCTS))
    res = {}
    for n, cell in enumerate(cells):
        key = tuple(cell[k] for k in NAMES)
        for p in PRODUCTS:
            r = run_cell(p, cell, bars(p))
            s = r.stats()
            s["date_from"], s["date_to"] = r.date_from, r.date_to
            res[(key, p)] = (s, r)
        if (n + 1) % 50 == 0:
            log.info("… %d/%d", n + 1, len(cells))
    one = [tuple(c[k] for k in NAMES) for c in one_step_cells()]
    pos = [k for k in one
           if all(res[(k, p)][0]["net_profit"] > 0 for p in PRODUCTS)]
    pct = 100 * len(pos) / len(one)
    base_key = tuple(BASELINE[k] for k in NAMES)
    base_exp = {p: expectancy(res[(base_key, p)][0]) for p in PRODUCTS}
    best_exp = {p: max(expectancy(res[(k, p)][0]) for k in one)
                for p in PRODUCTS}
    # one-directional 2× clause (b1_ruling precedent): fail only if the
    # baseline TOWERS over its neighborhood
    towering = any(base_exp[p] > 0 and best_exp[p] < base_exp[p] / 2
                   for p in PRODUCTS)
    passed = pct >= 60 and not towering
    detail = {"pos_both_pct": round(pct, 1), "pos_both": len(pos),
              "cells": len(one), "base_exp": base_exp, "best_exp": best_exp,
              "towering": towering}
    log.info("B1: %.1f%% ±1-step cells positive on both (≥60 needed); "
             "base exp %s; VERDICT %s", pct, base_exp,
             "PASS" if passed else "FAIL")
    record("or_b1_verdict", "MES,MNQ", detail,
           "PASS" if passed else "FAIL (needle)")
    return passed, res, pos


def stage_b_med(res, pos):
    med = []
    for j, k in enumerate(NAMES):
        vals = sorted((c[j] for c in pos),
                      key=lambda v: GRID[k].index(v))
        med.append(vals[len(vals) // 2])
    key = tuple(med)
    if key not in pos:
        key = min(pos, key=lambda c: sum(
            abs(idx(NAMES[j], c[j]) - idx(NAMES[j], med[j]))
            for j in range(len(NAMES))))
    cfg = dict(zip(NAMES, key))
    for p in PRODUCTS:
        s, r = res[(key, p)]
        record("or_B_med", p, cfg, "frozen plateau-median config", s)
        log.info("B_med %s: %s → %d trades net $%.2f win%% %.1f",
                 p, cfg, s["trades"], s["net_profit"], s["win_rate"] * 100)
    return cfg, {p: res[(key, p)][1] for p in PRODUCTS}


# ---------------------------------------------------------------- B2/B3

def stage_b2(base_runs):
    detail, ok, monthly = {}, True, {}
    for p, r in base_runs.items():
        trades = r.trades
        n = len(trades)
        net = sum(t.pnl_usd for t in trades)
        hours = Counter(datetime.fromisoformat(t.entry_ts).astimezone(ET).hour
                        for t in trades)
        news = sum(1 for t in trades
                   if any(abs((lambda d: d.hour * 60 + d.minute)(
                       datetime.fromisoformat(t.entry_ts).astimezone(ET)) - m)
                       <= 15 for m in (510, 600)))
        bym = defaultdict(float)
        for t in trades:
            bym[t.entry_ts[:7]] += t.pnl_usd
        monthly[p] = bym
        best = max((t.pnl_usd for t in trades), default=0.0)
        checks = {
            "trades": n,
            "top_hour_pct": round(100 * max(hours.values()) / n, 1) if n else 0,
            "news_pct": round(100 * news / n, 1) if n else 0,
            "max_month_pct": round(100 * max(bym.values()) / net, 1)
            if net > 0 and bym else 999,
            "net_wo_best": round(net - best, 2),
        }
        checks["ok"] = bool(checks["top_hour_pct"] <= 40
                            and checks["news_pct"] < 25
                            and checks["max_month_pct"] <= 50
                            and checks["net_wo_best"] > 0)
        ok = ok and checks["ok"]
        detail[p] = checks
    months = sorted(set(monthly["MES"]) | set(monthly["MNQ"]))
    agree = sum(1 for m in months
                if (monthly["MES"].get(m, 0) >= 0)
                == (monthly["MNQ"].get(m, 0) >= 0))
    detail["monthly_sign_agreement"] = f"{agree}/{len(months)}"
    ok = ok and agree >= 6
    log.info("B2: %s → %s", json.dumps(detail),
             "PASS" if ok else "FAIL (fragile_distribution)")
    record("or_b2", "MES,MNQ", detail, "PASS" if ok else "FAIL")
    return ok


def stage_b3(cfg):
    nets = {}
    for tag, kw in (("slip_x2", {"slippage": 4}),
                    ("comm_x1.5", {"commission": 1.65}),
                    ("both", {"slippage": 4, "commission": 1.65})):
        nets[tag] = {p: round(run_cell(p, cfg, bars(p), **kw)
                              .stats()["net_profit"], 2) for p in PRODUCTS}
        log.info("B3 %-9s %s", tag, nets[tag])
    ok = all(v > 0 for v in nets["both"].values())
    log.info("B3 VERDICT: %s", "PASS" if ok else "FAIL (no_cost_margin)")
    record("or_b3", "MES,MNQ", nets, "PASS" if ok else "FAIL")
    return ok


# ---------------------------------------------------------------- B4

def stage_b4(med_cfg):
    cells = one_step_cells()
    folds_out = {p: [] for p in PRODUCTS}
    for fi, (t0, t1, o0, o1) in enumerate(FOLDS, 1):
        for p in PRODUCTS:
            tune = bars(p, t0, t1)
            best_cell, best_e = med_cfg, None
            for cell in cells:
                s = run_cell(p, cell, tune).stats()
                if s["trades"] >= 8:
                    e = expectancy(s)
                    if best_e is None or e > best_e:
                        best_cell, best_e = cell, e
            oos = run_cell(p, best_cell, bars(p, o0, o1)).stats()
            folds_out[p].append({"fold": fi, "oos": f"{o0}..{o1}",
                                 "cell": best_cell,
                                 "tuned_exp": round(best_e or 0, 2),
                                 "oos_net": round(oos["net_profit"], 2),
                                 "oos_trades": oos["trades"]})
            log.info("B4 f%d %s: tuned %s → OOS net $%.2f (%d trades)",
                     fi, p, best_cell, oos["net_profit"], oos["trades"])
    ok = True
    summary = {}
    for p in PRODUCTS:
        nets = [f["oos_net"] for f in folds_out[p]]
        agg = sum(nets)
        nonneg = sum(1 for v in nets if v >= 0)
        winners = [v for v in nets if v > 0]
        worst = min(nets)
        cap_ok = (not winners) or (worst >= -2 * (sum(winners) / len(winners)))
        p_ok = agg > 0 and nonneg >= 4 and cap_ok
        ok = ok and p_ok
        summary[p] = {"oos_agg": round(agg, 2), "folds_nonneg": nonneg,
                      "worst_fold": worst, "ok": p_ok}
        log.info("B4 %s: aggregate OOS $%.2f, %d/6 non-negative → %s",
                 p, agg, nonneg, "ok" if p_ok else "FAIL")
    record("or_b4_wf", "MES,MNQ", {"folds": folds_out, "summary": summary},
           "PASS" if ok else "FAIL (not_findable_in_advance)")
    return ok


# ---------------------------------------------------------------- B5

def stage_b5(cfg, base_runs):
    band = {}
    rng = np.random.default_rng(20260823)
    for p, r in base_runs.items():
        pnls = np.array([t.pnl_usd for t in r.trades])
        boots = [rng.choice(pnls, size=len(pnls), replace=True).mean()
                 for _ in range(10_000)]
        band[p] = [round(float(np.percentile(boots, 5)), 2),
                   round(float(np.percentile(boots, 95)), 2)]
    record("or_holdout_band", "MES,MNQ",
           {"config": cfg, "band_90pct_expectancy": band},
           "pre-registered BEFORE the holdout run")
    log.info("B5 pre-registered 90%% expectancy bands: %s", band)

    verdict_ok = True
    detail = {"config": cfg, "band": band}
    for p in PRODUCTS:
        r = run_cell(p, cfg, bars(p, HOLDOUT_FROM, HOLDOUT_TO))
        s = r.stats()
        s["date_from"], s["date_to"] = r.date_from, r.date_to
        e = expectancy(s)
        lo, hi = band[p]
        in_band = lo <= e <= hi
        verdict_ok = verdict_ok and in_band
        detail[p] = {"trades": s["trades"], "net": round(s["net_profit"], 2),
                     "expectancy": round(e, 2), "in_band": in_band}
        record("or_holdout", p, detail[p],
               "ONE-SHOT holdout run", s)
        log.info("B5 HOLDOUT %s: %d trades net $%.2f exp $%.2f/trade "
                 "band [%.2f, %.2f] → %s", p, s["trades"], s["net_profit"],
                 e, lo, hi, "IN BAND" if in_band else "OUT OF BAND")
    record("or_final_verdict", "MES,MNQ", detail,
           "PASS" if verdict_ok else "FAIL (holdout_collapse)")
    log.info("B5 VERDICT: %s", "PASS" if verdict_ok else "FAIL")
    return verdict_ok


def main() -> int:
    ok, res, pos = stage_b1()
    if not ok:
        log.info("pipeline STOPPED at B1 — holdout stays sealed")
        return 1
    cfg, base_runs = stage_b_med(res, pos)
    if not stage_b2(base_runs):
        log.info("pipeline STOPPED at B2 — holdout stays sealed")
        return 1
    if not stage_b3(cfg):
        log.info("pipeline STOPPED at B3 — holdout stays sealed")
        return 1
    if not stage_b4(cfg):
        log.info("pipeline STOPPED at B4 — holdout stays sealed")
        return 1
    log.info("B1-B4 all PASS — proceeding to the ONE-SHOT holdout "
             "(pre-authorized 2026-08-23)")
    return 0 if stage_b5(cfg, base_runs) else 1


if __name__ == "__main__":
    sys.exit(main())
