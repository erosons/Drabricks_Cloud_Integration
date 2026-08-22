"""Run the §9 tick backtester over pulled Databento TBBO history.

    python scripts/backtest.py --product MES \
        --data-dir data/databento/GLBX-20260820-6YB3TN8MD6
    python scripts/backtest.py --product MES --from 2025-09-01 --to 2025-09-30

HOLDOUT DISCIPLINE: the last ~3 months of the pulled year
(>= 2026-05-20) are the out-of-sample holdout. Runs that touch them are
refused unless --holdout is passed explicitly — touch it once, at the
end, or it stops being evidence (§10).

Results: stats printed, run persisted to backtest_runs (kind
"limited"), per-trade CSV written next to the log (--csv to override).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config_loader import load_config
from src.research.backtester import Backtester, load_tbbo_dir
from src.storage.db import Database
from src.utils.logger import get_logger

log = get_logger("backtest")

HOLDOUT_START = "2026-05-20"        # last 3 months of the 2025-08-20 pull


async def amain() -> int:
    parser = argparse.ArgumentParser(description="tick backtest (§9)")
    parser.add_argument("--product", default="MES")
    parser.add_argument("--data-dir", default=None,
                        help="Databento batch dir of *.tbbo.dbn.zst "
                             "(default: newest dir under data/databento "
                             "containing tbbo files)")
    parser.add_argument("--from", dest="date_from", default=None)
    parser.add_argument("--to", dest="date_to", default=None)
    parser.add_argument("--holdout", action="store_true",
                        help="allow the run to touch the holdout window")
    parser.add_argument("--slippage-ticks", type=int, default=2)
    parser.add_argument("--commission", type=float, default=1.10,
                        help="USD per side per contract")
    parser.add_argument("--csv", default=None, help="per-trade CSV path")
    parser.add_argument("--config-dir", default=str(ROOT / "config"))
    args = parser.parse_args()

    touches_holdout = args.date_to is None or args.date_to >= HOLDOUT_START
    if touches_holdout and not args.holdout:
        if args.date_to is None:
            args.date_to = "2026-05-19"
            log.warning("no --to given — capped at %s to protect the "
                        "holdout (pass --holdout to override)", args.date_to)
        else:
            log.error("--to %s reaches into the holdout (>= %s); pass "
                      "--holdout to run it deliberately",
                      args.date_to, HOLDOUT_START)
            return 2

    data_dir = args.data_dir
    if data_dir is None:
        candidates = sorted(
            d for d in (ROOT / "data" / "databento").iterdir()
            if d.is_dir() and list(d.glob("*.tbbo.dbn.zst")))
        by_product = [d for d in candidates
                      if args.product in json.loads(
                          (d / "metadata.json").read_text()
                      ).get("query", {}).get("symbols", ["?"])[0]]
        if not by_product:
            log.error("no TBBO batch dir found for %s under data/databento "
                      "— pass --data-dir", args.product)
            return 2
        data_dir = by_product[-1]
    log.info("data: %s | window: %s..%s | slippage=%d ticks, "
             "commission=$%.2f/side", data_dir, args.date_from or "start",
             args.date_to or "end", args.slippage_ticks, args.commission)

    config = load_config(args.config_dir)
    bt = Backtester(config, args.product,
                    slippage_ticks=args.slippage_ticks,
                    commission_per_side=args.commission)
    result = await bt.run(load_tbbo_dir(data_dir, args.date_from,
                                        args.date_to))

    stats = result.stats()
    log.info("==== %s %s..%s (%d ticks) ====", result.product,
             result.date_from, result.date_to, result.ticks)
    for key, val in stats.items():
        log.info("  %-14s %s", key,
                 f"{val:.2f}" if isinstance(val, float) else val)
    log.info("  gate skips     %s", result.skips)
    log.info("  fill flags     %s", result.fill_flags)

    db = Database(ROOT / config.raw["database"]["path"])
    run_id = result.persist(db)
    log.info("persisted to backtest_runs id=%d", run_id)

    csv_path = Path(args.csv) if args.csv else (
        ROOT / "logs" / f"backtest_{result.product}_{result.date_from}"
                        f"_{result.date_to}_run{run_id}.csv")
    with open(csv_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["side", "qty", "entry_ts", "entry_price", "exit_ts",
                         "exit_price", "exit_reason", "fees", "pnl_usd"])
        for t in result.closed:
            writer.writerow([t.side, t.qty, t.entry_ts, t.entry_price,
                             t.exit_ts, t.exit_price, t.exit_reason,
                             f"{t.fees:.2f}", f"{t.pnl_usd:.2f}"])
    log.info("per-trade CSV: %s", csv_path)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
