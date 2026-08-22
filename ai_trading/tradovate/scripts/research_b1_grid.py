"""Workstream B1 — ema_sr_break parameter robustness grid (research spec).

Grid: 5 values per tunable (baseline, ±1, ±2 steps). Full cartesian
(3,125 × 2 products) exceeds the spec's ~2,000 cap, so per spec: the
complete ±1-step fractional grid (3^5 = 243 combos — the cells the
plateau verdict is defined over) plus one-at-a-time ±2-step sweeps.

Pre-committed verdict (frozen in the spec, evaluated by this script):
  PASS (plateau): ≥ 60% of ±1-step cells net-positive after fees on
    BOTH products, AND best-cell expectancy ≤ 2× baseline expectancy.
  FAIL (needle): otherwise.

Every run persists to backtest_runs + research_results phase 'b1_grid'
(params in flags_json); baseline frozen first as phase 'B_base'.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config_loader import load_config
from src.research.bar_backtester import BarBracketSim
from src.research.bars import add_session_columns, load_bars
from src.research.card_strategies import EmaSrBreak
from src.storage.db import Database
from src.utils.logger import get_logger

log = get_logger("b1_grid")

GRID = {
    "ema_fast": [5, 7, 9, 11, 13],
    "ema_slow": [15, 18, 21, 24, 27],
    "min_sep_atr": [0.15, 0.20, 0.25, 0.30, 0.35],
    "target_rr": [1.5, 1.75, 2.0, 2.25, 2.5],
    "swing_lookback": [3, 4, 5, 6, 7],
}
BASELINE = {"ema_fast": 9, "ema_slow": 21, "min_sep_atr": 0.25,
            "target_rr": 2.0, "swing_lookback": 5}
DATE_TO = "2026-05-19"          # dev set only — holdout sealed


def combos() -> list[dict]:
    names = list(GRID)
    base_idx = {k: GRID[k].index(BASELINE[k]) for k in names}
    out, seen = [], set()

    def add(c):
        key = tuple(c[k] for k in names)
        if key not in seen:
            seen.add(key)
            out.append(dict(c))

    # full ±1-step fractional grid (verdict cells)
    for vals in itertools.product(*[
            [GRID[k][j] for j in (base_idx[k] - 1, base_idx[k],
                                  base_idx[k] + 1)] for k in names]):
        add(dict(zip(names, vals)))
    # one-at-a-time ±2-step sweeps
    for k in names:
        for j in (base_idx[k] - 2, base_idx[k] + 2):
            c = dict(BASELINE)
            c[k] = GRID[k][j]
            add(c)
    return out


def persist(db, result, phase, params):
    s = result.stats()
    now = datetime.now(timezone.utc).isoformat()
    cur = db.conn.execute(
        "INSERT INTO backtest_runs (strategy, product, kind, params_json,"
        " date_from, date_to, net_profit, max_drawdown, trades,"
        " largest_loss, fill_flags_json, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("ema_sr_break", result.product, "b1_grid", json.dumps(params),
         result.date_from, result.date_to, s["net_profit"],
         s["max_drawdown"], s["trades"], s["largest_loss"],
         json.dumps(result.flags), now))
    db.conn.execute(
        "INSERT INTO research_results (run_id, strategy, product, phase,"
        " timeframe_min, date_from, date_to, trades, wins, losses, win_rate,"
        " net_profit, fees, profit_factor, max_drawdown, largest_loss,"
        " flags_json, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cur.lastrowid, "ema_sr_break", result.product, phase, 5,
         result.date_from, result.date_to, s["trades"], s["wins"],
         s["losses"], s["win_rate"], s["net_profit"], s["fees"],
         min(s["profit_factor"], 999.0), s["max_drawdown"],
         s["largest_loss"], json.dumps(params), "b1 grid cell", now))
    return s


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--products", default="MES,MNQ")
    parser.add_argument("--config-dir", default=str(ROOT / "config"))
    args = parser.parse_args()

    config = load_config(args.config_dir)
    db = Database(ROOT / config.raw["database"]["path"])
    products = args.products.split(",")
    cells = combos()
    log.info("grid: %d combos × %d products (dev set → %s)",
             len(cells), len(products), DATE_TO)

    bars = {}
    for prod in products:
        df = load_bars(prod, 5, ROOT / "data" / "databento",
                       None, DATE_TO)
        bars[prod] = add_session_columns(df, config.raw["session"])

    results: dict[tuple, dict] = {}     # (combo_key, product) -> stats
    names = list(GRID)
    for n, combo in enumerate(cells):
        key = tuple(combo[k] for k in names)
        phase = "B_base" if combo == BASELINE else "b1_grid"
        for prod in products:
            product = config.products[prod]
            params = {**config.strategies["ema_sr_break"].params, **combo}
            strat = EmaSrBreak(params, product)
            df = strat.prepare(bars[prod].copy())
            result = BarBracketSim(strat, product, df).run()
            results[(key, prod)] = persist(db, result, phase, combo)
        if (n + 1) % 25 == 0:
            log.info("… %d/%d combos", n + 1, len(cells))
    db.conn.commit()

    # ---- pre-committed verdict ----
    base_key = tuple(BASELINE[k] for k in names)
    one_step_cells = [tuple(c[k] for k in names) for c in cells
                      if all(abs(GRID[k].index(c[k])
                                 - GRID[k].index(BASELINE[k])) <= 1
                             for k in names)]
    pos_both = [k for k in one_step_cells
                if all(results[(k, p)]["net_profit"] > 0 for p in products)]
    pct = 100 * len(pos_both) / len(one_step_cells)

    def expectancy(k, p):
        s = results[(k, p)]
        return s["net_profit"] / s["trades"] if s["trades"] else 0.0

    base_exp = {p: expectancy(base_key, p) for p in products}
    best_exp = {p: max(expectancy(k, p) for k in one_step_cells)
                for p in products}
    plateau = pct >= 60
    not_needle_peak = all(
        base_exp[p] > 0 and best_exp[p] <= 2 * base_exp[p]
        for p in products)
    verdict = "PASS (plateau)" if plateau and not_needle_peak \
        else "FAIL (needle)"

    log.info("=" * 66)
    log.info("B1 VERDICT: %s", verdict)
    log.info("  ±1-step cells net-positive on BOTH products: %d/%d (%.1f%%)"
             "  [threshold ≥60%%]", len(pos_both), len(one_step_cells), pct)
    for p in products:
        s = results[(base_key, p)]
        log.info("  %s baseline: %d trades  net $%.2f  exp $%.2f/trade  "
                 "best ±1 cell exp $%.2f  (peak cap 2×: %s)",
                 p, s["trades"], s["net_profit"], base_exp[p], best_exp[p],
                 "ok" if base_exp[p] > 0 and best_exp[p] <= 2 * base_exp[p]
                 else "VIOLATED")
    neg_adjacent = sum(1 for k in one_step_cells
                       if any(results[(k, p)]["net_profit"] < 0
                              for p in products))
    log.info("  cells negative on ≥1 product: %d/%d", neg_adjacent,
             len(one_step_cells))
    db.conn.execute(
        "INSERT INTO research_results (strategy, product, phase, trades,"
        " net_profit, flags_json, notes, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        ("ema_sr_break", ",".join(products), "b1_verdict",
         len(one_step_cells), pct, json.dumps(
             {"pos_both_pct": pct, "base_exp": base_exp,
              "best_exp": best_exp}),
         verdict, datetime.now(timezone.utc).isoformat()))
    db.conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
