"""Run every playbook-card strategy over the dev set — the G2 screen.

    python scripts/backtest_cards.py                       # all × MES,MNQ
    python scripts/backtest_cards.py --products MES
    python scripts/backtest_cards.py --strategies supertrend_rsi,pivot_levels
    python scripts/backtest_cards.py --phase L1-bars

Same holdout discipline as backtest.py: the window is capped at
2026-05-19 unless --holdout. Every run lands in research_results (full
stat block + the card's bar-level interpretation notes) and
backtest_runs (summary ledger); `v_research_summary` ranks the latest
run per (strategy, product, phase).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config_loader import load_config
from src.research.bar_backtester import BarBracketSim
from src.research.bars import add_session_columns, load_bars
from src.research.card_strategies import ALL_STRATEGIES, GATES
from src.storage.db import Database
from src.utils.logger import get_logger

log = get_logger("backtest_cards")

HOLDOUT_START = "2026-05-20"


def persist(db: Database, result, phase: str, params: dict,
            notes: str) -> int:
    s = result.stats()
    cur = db.conn.execute(
        "INSERT INTO backtest_runs (strategy, product, kind, params_json,"
        " date_from, date_to, net_profit, max_drawdown, trades,"
        " largest_loss, fill_flags_json, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (result.strategy, result.product, "limited", json.dumps(params),
         result.date_from, result.date_to, s["net_profit"],
         s["max_drawdown"], s["trades"], s["largest_loss"],
         json.dumps(result.flags), datetime.now(timezone.utc).isoformat()))
    run_id = cur.lastrowid
    db.conn.execute(
        "INSERT INTO research_results (run_id, strategy, product, phase,"
        " timeframe_min, date_from, date_to, trades, wins, losses, win_rate,"
        " net_profit, fees, profit_factor, max_drawdown, largest_loss,"
        " flags_json, notes, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, result.strategy, result.product, phase,
         result.timeframe_min, result.date_from, result.date_to,
         s["trades"], s["wins"], s["losses"], s["win_rate"],
         s["net_profit"], s["fees"],
         min(s["profit_factor"], 999.0), s["max_drawdown"],
         s["largest_loss"], json.dumps(result.flags), notes,
         datetime.now(timezone.utc).isoformat()))
    db.conn.commit()
    return run_id


async def amain() -> int:
    parser = argparse.ArgumentParser(description="card-strategy G2 screen")
    parser.add_argument("--products", default="MES,MNQ")
    parser.add_argument("--strategies", default=None,
                        help="comma list (default: all cards)")
    parser.add_argument("--from", dest="date_from", default=None)
    parser.add_argument("--to", dest="date_to", default=None)
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--phase", default="L1-bars")
    parser.add_argument("--slippage-ticks", type=int, default=2)
    parser.add_argument("--commission", type=float, default=1.10)
    parser.add_argument("--config-dir", default=str(ROOT / "config"))
    args = parser.parse_args()

    if not args.holdout and (args.date_to is None
                             or args.date_to >= HOLDOUT_START):
        args.date_to = "2026-05-19"
        log.warning("window capped at %s to protect the holdout "
                    "(--holdout to override)", args.date_to)

    config = load_config(args.config_dir)
    db = Database(ROOT / config.raw["database"]["path"])
    names = (args.strategies.split(",") if args.strategies
             else list(ALL_STRATEGIES))
    products = args.products.split(",")

    bar_cache: dict[tuple, object] = {}

    def bars_for(product: str, tf: int):
        key = (product, tf)
        if key not in bar_cache:
            df = load_bars(product, tf, ROOT / "data" / "databento",
                           args.date_from, args.date_to)
            bar_cache[key] = add_session_columns(
                df, config.raw["session"])
        return bar_cache[key].copy()

    rows = []
    for product_symbol in products:
        product = config.products[product_symbol]
        for name in names:
            if name in GATES:
                log.info("%-22s %s: GATE — judged by improvement added, "
                         "not standalone (card); skipped", name,
                         product_symbol)
                continue
            cls = ALL_STRATEGIES[name]
            strat_params = config.strategies[name].params
            strategy = cls(strat_params, product)
            df = bars_for(product_symbol, strategy.timeframe_min)
            df = strategy.prepare(df)
            sim = BarBracketSim(strategy, product, df,
                                args.slippage_ticks, args.commission)
            result = sim.run()
            s = result.stats()
            run_id = persist(db, result, args.phase,
                             {"slippage_ticks": args.slippage_ticks,
                              "commission_per_side": args.commission,
                              **{k: v for k, v in strat_params.items()
                                 if isinstance(v, (int, float, str, bool))}},
                             strategy.notes)
            rows.append((name, product_symbol, s, run_id))
            log.info("%-22s %s: %3d trades  win%% %5.1f  net $%9.2f  "
                     "PF %5.2f  maxDD $%8.2f  (run %d)",
                     name, product_symbol, s["trades"],
                     s["win_rate"] * 100, s["net_profit"],
                     min(s["profit_factor"], 99), s["max_drawdown"], run_id)

    log.info("=" * 74)
    log.info("RANKED (net profit) — phase %s, %s..%s", args.phase,
             args.date_from or "start", args.date_to)
    for name, prod, s, run_id in sorted(rows, key=lambda r: -r[2]["net_profit"]):
        log.info("%-22s %-4s net $%9.2f  %3d trades  win%% %5.1f  PF %5.2f",
                 name, prod, s["net_profit"], s["trades"],
                 s["win_rate"] * 100, min(s["profit_factor"], 99))
    log.info("full table: SELECT * FROM v_research_summary;")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
