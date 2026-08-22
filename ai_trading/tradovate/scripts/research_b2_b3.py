"""Workstreams B2 (distribution sanity) + B3 (cost stress) — research spec.

Runs after the human B1 ruling (2026-08-22): B1 continues on the
PROSE-INTENT reading — the plateau clause passed (69.1%); the 2× clause
fired in the reverse direction of its purpose (baseline below its
neighborhood, not towering over it). Precedent recorded: that clause is
one-directional; a below-average baseline inside a positive plateau is
not needle evidence.

Going-forward config = the PLATEAU MEDIAN cell (component-wise median of
the ±1-step cells net-positive on BOTH products, snapped to the grid,
nearest positive cell if the snap lands outside the zone) — never the
best cell; trusting the neighborhood, not one lucky address. Frozen here
as phase 'B_med' before B2/B3 run.

B2 (per spec, on B_med trade lists, both products):
  - no single ET hour > 40% of entries; < 25% of entries inside news
    windows (proxy ±15 min around 08:30/10:00 ET)
  - no single month > 50% of total net P&L; removing the single best
    trade leaves the strategy net-positive
  - MES and MNQ monthly P&L signs agree in ≥ 6 of 9 months
B3: rerun B_med under (a) slippage ×2, (b) commissions ×1.5, (c) both.
  PASS: net-positive on both products under (c).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config_loader import load_config
from src.research.bar_backtester import BarBracketSim
from src.research.bars import add_session_columns, load_bars
from src.research.card_strategies import EmaSrBreak
from src.storage.db import Database
from src.utils.logger import get_logger

log = get_logger("b2_b3")

GRID = {
    "ema_fast": [5, 7, 9, 11, 13],
    "ema_slow": [15, 18, 21, 24, 27],
    "min_sep_atr": [0.15, 0.20, 0.25, 0.30, 0.35],
    "target_rr": [1.5, 1.75, 2.0, 2.25, 2.5],
    "swing_lookback": [3, 4, 5, 6, 7],
}
DATE_TO = "2026-05-19"
ET = ZoneInfo("America/New_York")
PRODUCTS = ("MES", "MNQ")


def plateau_median(db: Database) -> dict:
    """Component-wise median of the ±1-step cells positive on BOTH
    products, snapped to grid; nearest positive cell if outside zone."""
    names = list(GRID)
    rows = db.conn.execute(
        "SELECT product, net_profit, flags_json FROM research_results "
        "WHERE strategy='ema_sr_break' AND phase IN ('b1_grid','B_base')"
    ).fetchall()
    nets: dict[tuple, dict] = defaultdict(dict)
    for r in rows:
        params = json.loads(r["flags_json"])
        key = tuple(params[k] for k in names)
        nets[key][r["product"]] = r["net_profit"]
    positive = [k for k, v in nets.items()
                if all(v.get(p, -1) > 0 for p in PRODUCTS)]
    med = []
    for j, k in enumerate(names):
        vals = sorted(c[j] for c in positive)
        med.append(vals[len(vals) // 2])
    key = tuple(min(GRID[names[j]], key=lambda g: abs(g - med[j]))
                for j in range(len(names)))
    if key not in positive:
        key = min(positive, key=lambda c: (
            sum(abs(GRID[names[j]].index(c[j])
                    - GRID[names[j]].index(key[j]))
                for j in range(len(names))),
            -sum(nets[c][p] for p in PRODUCTS)))
    cfg = dict(zip(names, key))
    log.info("plateau: %d positive-on-both cells; median cell: %s "
             "(dev nets: %s)", len(positive), cfg,
             {p: round(nets[key][p], 2) for p in PRODUCTS})
    return cfg


def run_cfg(config, product_symbol, cfg, bars, slippage=2, commission=1.10):
    product = config.products[product_symbol]
    params = {**config.strategies["ema_sr_break"].params, **cfg}
    strat = EmaSrBreak(params, product)
    df = strat.prepare(bars[product_symbol].copy())
    return BarBracketSim(strat, product, df, slippage_ticks=slippage,
                         commission_per_side=commission).run()


def et_fields(ts: str) -> tuple[int, int, str]:
    dt = datetime.fromisoformat(ts).astimezone(ET)
    return dt.hour, dt.hour * 60 + dt.minute, dt.strftime("%Y-%m")


def b2_checks(results: dict) -> tuple[bool, dict]:
    detail, ok = {}, True
    monthly = {}
    for prod, res in results.items():
        trades = res.trades
        hours = Counter()
        news = 0
        by_month: dict[str, float] = defaultdict(float)
        for t in trades:
            hour, minutes, month = et_fields(t.entry_ts)
            hours[hour] += 1
            if any(abs(minutes - m) <= 15 for m in (510, 600)):
                news += 1
            by_month[month] += t.pnl_usd
        n = len(trades)
        net = sum(t.pnl_usd for t in trades)
        top_hour_pct = 100 * max(hours.values()) / n if n else 0
        news_pct = 100 * news / n if n else 0
        month_shares = {m: v / net for m, v in by_month.items()} if net > 0 \
            else {}
        max_month_pct = 100 * max(month_shares.values()) if month_shares \
            else 999
        best = max((t.pnl_usd for t in trades), default=0)
        wo_best = net - best
        checks = {
            "top_hour_pct": round(float(top_hour_pct), 1),
            "top_hour_ok": bool(top_hour_pct <= 40),
            "news_pct": round(float(news_pct), 1),
            "news_ok": bool(news_pct < 25),
            "max_month_pct_of_net": round(float(max_month_pct), 1),
            "month_ok": bool(max_month_pct <= 50),
            "net_without_best_trade": round(float(wo_best), 2),
            "wo_best_ok": bool(wo_best > 0),
        }
        ok = ok and all(v for k, v in checks.items() if k.endswith("_ok"))
        detail[prod] = checks
        monthly[prod] = by_month
    months = sorted(set(monthly["MES"]) | set(monthly["MNQ"]))
    agree = sum(1 for m in months
                if (monthly["MES"].get(m, 0) >= 0)
                == (monthly["MNQ"].get(m, 0) >= 0))
    detail["monthly_sign_agreement"] = f"{agree}/{len(months)}"
    coher_ok = agree >= 6
    ok = ok and coher_ok
    detail["coherence_ok"] = coher_ok
    return ok, detail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", default=str(ROOT / "config"))
    args = parser.parse_args()
    config = load_config(args.config_dir)
    db = Database(ROOT / config.raw["database"]["path"])
    now = datetime.now(timezone.utc).isoformat()

    # ---- the human B1 ruling + precedent, of record ----
    db.conn.execute(
        "INSERT INTO research_results (strategy, product, phase, trades,"
        " net_profit, flags_json, notes, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        ("ema_sr_break", "MES,MNQ", "b1_ruling", 0, 0.0,
         json.dumps({"ruling": "continue on prose intent"}),
         "HUMAN RULING 2026-08-22: B1 continues. The 2x-expectancy clause "
         "is a smoke detector for fake profits (baseline towering over dead "
         "neighbors); it beeped on the reverse case (baseline below a "
         "broadly positive plateau) — steam, not fire. PRECEDENT: the "
         "clause is one-directional. Going-forward config = plateau MEDIAN "
         "cell, never the best cell (a best cell chosen from the same 9 "
         "months is the exact lucky-dial mistake the test exists to catch).",
         now))
    db.conn.commit()

    cfg = plateau_median(db)
    bars = {}
    for prod in PRODUCTS:
        df = load_bars(prod, 5, ROOT / "data" / "databento", None, DATE_TO)
        bars[prod] = add_session_columns(df, config.raw["session"])

    # ---- freeze B_med ----
    base = {}
    for prod in PRODUCTS:
        res = run_cfg(config, prod, cfg, bars)
        s = res.stats()
        base[prod] = res
        db.conn.execute(
            "INSERT INTO research_results (strategy, product, phase,"
            " timeframe_min, date_from, date_to, trades, wins, losses,"
            " win_rate, net_profit, fees, profit_factor, max_drawdown,"
            " largest_loss, flags_json, notes, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("ema_sr_break", prod, "B_med", 5, res.date_from, res.date_to,
             s["trades"], s["wins"], s["losses"], s["win_rate"],
             s["net_profit"], s["fees"], min(s["profit_factor"], 999.0),
             s["max_drawdown"], s["largest_loss"], json.dumps(cfg),
             "frozen going-forward config: plateau median", now))
        log.info("B_med %s: %d trades  net $%.2f  win%% %.1f  PF %.2f",
                 prod, s["trades"], s["net_profit"], s["win_rate"] * 100,
                 min(s["profit_factor"], 99))
    db.conn.commit()

    # ---- B2 ----
    b2_ok, b2_detail = b2_checks(base)
    log.info("B2 detail: %s", json.dumps(b2_detail))
    log.info("B2 VERDICT: %s", "PASS" if b2_ok else "FAIL (fragile_distribution)")

    # ---- B3 ----
    stresses = {"a_slip_x2": {"slippage": 4},
                "b_comm_x1.5": {"commission": 1.65},
                "c_both": {"slippage": 4, "commission": 1.65}}
    b3 = {}
    for tag, kw in stresses.items():
        b3[tag] = {}
        for prod in PRODUCTS:
            s = run_cfg(config, prod, cfg, bars, **kw).stats()
            b3[tag][prod] = round(s["net_profit"], 2)
        log.info("B3 %-12s nets: %s", tag, b3[tag])
    b3_ok = all(v > 0 for v in b3["c_both"].values())
    log.info("B3 VERDICT: %s", "PASS" if b3_ok else "FAIL (no_cost_margin)")

    for phase, ok, detail in (("b2_sanity", b2_ok, b2_detail),
                              ("b3_cost", b3_ok, b3)):
        db.conn.execute(
            "INSERT INTO research_results (strategy, product, phase, trades,"
            " net_profit, flags_json, notes, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            ("ema_sr_break", "MES,MNQ", phase, 0, 0.0, json.dumps(detail),
             "PASS" if ok else "FAIL", now))
    db.conn.commit()
    return 0 if (b2_ok and b3_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
