"""Phase-2 depth study: order_flow_scalp at book_depth 10 vs 1.

    python scripts/depth_study.py                    # MES month, both arms
    python scripts/depth_study.py --product MNQ

Replays the pulled MBP-10 month (trade events carrying the full 10-level
book) through the SAME order-flow engine twice — book_depth 10 vs 1 —
and persists both arms to research_results (phases L2-depth10 /
L2-depth1). This answers the standing question from the Databento plan
choice: does real depth produce signals that top-of-book cannot (and
would the Plus tier ever pay for itself)?

Both arms see identical decision points (trade events); only the
imbalance depth differs. NOTE: the MBP-10 window (2026-07-19..08-19)
overlaps the TBBO holdout — acceptable because this is an A/B on fixed
params, not tuning; recorded in the run flags.
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
from src.research.backtester import Backtester, load_mbp10_trades
from src.storage.db import Database
from src.utils.logger import get_logger

log = get_logger("depth_study")

MBP10_DIRS = {"MES": "GLBX-20260820-JMRK9LJMSH",
              "MNQ": "GLBX-20260820-D5MVYKS73X"}


async def amain() -> int:
    parser = argparse.ArgumentParser(description="depth-10 vs depth-1 A/B")
    parser.add_argument("--product", default="MES")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--depths", default="10,1")
    parser.add_argument("--config-dir", default=str(ROOT / "config"))
    args = parser.parse_args()

    data_dir = args.data_dir or (
        ROOT / "data" / "databento" / MBP10_DIRS[args.product])
    config = load_config(args.config_dir)
    db = Database(ROOT / config.raw["database"]["path"])

    results = {}
    for depth in (int(d) for d in args.depths.split(",")):
        log.info("==== arm: book_depth=%d ====", depth)
        bt = Backtester(config, args.product,
                        param_overrides={"book_depth": depth})
        result = await bt.run(load_mbp10_trades(data_dir),
                              progress_every=2_000_000)
        s = result.stats()
        result.fill_flags["holdout_overlap"] = "A/B on fixed params, not tuning"
        run_id = result.persist(db, kind="depth_study")
        db.conn.execute(
            "INSERT INTO research_results (run_id, strategy, product, phase,"
            " timeframe_min, date_from, date_to, trades, wins, losses,"
            " win_rate, net_profit, fees, profit_factor, max_drawdown,"
            " largest_loss, flags_json, notes, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, "order_flow_scalp", args.product, f"L2-depth{depth}",
             0, result.date_from, result.date_to, s["trades"], s["wins"],
             s["losses"], s["win_rate"], s["net_profit"], s["fees"],
             min(s["profit_factor"], 999.0), s["max_drawdown"],
             s["largest_loss"], json.dumps(result.fill_flags),
             "tick engine on MBP-10 trade events; book = full snapshot at "
             "each trade", datetime.now(timezone.utc).isoformat()))
        db.conn.commit()
        results[depth] = (s, result)
        log.info("depth=%d: %d trades  win%% %.1f  net $%.2f  skips=%s",
                 depth, s["trades"], s["win_rate"] * 100, s["net_profit"],
                 result.skips)

    log.info("=" * 60)
    log.info("DEPTH A/B — %s %s..%s", args.product,
             next(iter(results.values()))[1].date_from,
             next(iter(results.values()))[1].date_to)
    for depth, (s, result) in results.items():
        l1 = result.skips.get("L1_confidence", 0)
        l2 = result.skips.get("L2_price_action", 0)
        log.info("  depth %2d: trades %3d  win%% %5.1f  net $%9.2f  "
                 "L1_blocked %d  L2_blocked %d",
                 depth, s["trades"], s["win_rate"] * 100, s["net_profit"],
                 l1, l2)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
