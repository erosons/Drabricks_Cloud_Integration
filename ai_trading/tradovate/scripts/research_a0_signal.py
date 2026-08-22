"""Workstream A0 — order_flow_scalp signal predictiveness (research spec).

Replays the 9-month MES tick dev set through the L1 signal only — no
trading, no brackets. Records every fired signal (RTH, outside the news
proxy windows, 10s cooldown to match the engine's order cooldown) and
measures the forward mid-price move at +5/15/30/60s against a random-
tick baseline.

Pre-committed verdict (frozen in the spec):
  PASS: at ≥1 horizon, hit rate ≥ 53% AND mean signed forward move
        ≥ 0.5 tick above baseline, with ≥ 5,000 non-news signals.
  FAIL: anything less → stop; A1 does not run; strategy closes as
        signal_not_predictive.

News proxy (no historical calendar wired): ±15 min around 08:30 and
10:00 ET — recorded in the results as the spec requires.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zoneinfo import ZoneInfo

from src.config_loader import load_config
from src.market_data.orderbook import OrderBook
from src.research.backtester import load_tbbo_dir
from src.storage.db import Database
from src.trading.order_flow import OrderFlowAnalyzer
from src.trading.signals import Signal
from src.utils.logger import get_logger

log = get_logger("a0_signal")

HORIZONS_S = (5, 15, 30, 60)
COOLDOWN_NS = 10 * 1_000_000_000
BASELINE_EVERY = 5_000
ET = ZoneInfo("America/New_York")
DATE_TO = "2026-05-19"


def in_rth_and_news(ts_ns: int) -> tuple[bool, bool]:
    local = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc).astimezone(ET)
    minutes = local.hour * 60 + local.minute
    rth = local.weekday() < 5 and 8 * 60 <= minutes < 16 * 60
    news = any(abs(minutes - m) <= 15 for m in (8 * 60 + 30, 10 * 60))
    return rth, news


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", default="MES")
    parser.add_argument("--data-dir",
                        default="data/databento/GLBX-20260820-6YB3TN8MD6")
    parser.add_argument("--config-dir", default=str(ROOT / "config"))
    args = parser.parse_args()

    config = load_config(args.config_dir)
    params = config.strategies["order_flow_scalp"].params
    tick_size = config.products[args.product].tick_size
    analyzer = OrderFlowAnalyzer(
        imbalance_threshold=params["imbalance_threshold"],
        book_depth=params["book_depth"],
        min_confidence=params["min_confidence"])
    book = OrderBook("A0", tick_size)

    # pending[horizon] = deque of [due_ns, direction, mid, kind]
    pending = {h: deque() for h in HORIZONS_S}
    stats = {h: {"signal": [0, 0, 0.0], "baseline": [0, 0, 0.0]}
             for h in HORIZONS_S}      # [n, hits, sum_signed_move_ticks]
    counts = {"signals": 0, "news_excluded": 0, "baseline": 0}
    last_signal_ns = 0
    rng_dir = 1
    n = 0

    for tick in load_tbbo_dir(args.data_dir, None, DATE_TO):
        n += 1
        book.apply_dom({"bids": [{"price": tick.bid, "size": tick.bid_sz}],
                        "asks": [{"price": tick.ask, "size": tick.ask_sz}]})
        mid = (tick.bid + tick.ask) / 2

        for h in HORIZONS_S:            # resolve matured observations
            q = pending[h]
            while q and tick.ts_ns >= q[0][0]:
                _, direction, mid0, kind = q.popleft()
                move = (mid - mid0) / tick_size * direction
                rec = stats[h][kind]
                rec[0] += 1
                rec[1] += move > 0
                rec[2] += move

        # engine parity: analyze against the book BEFORE adding this trade
        flow = analyzer.analyze(book)
        if flow.signal is not Signal.NEUTRAL \
                and flow.confidence >= analyzer.min_confidence \
                and tick.ts_ns - last_signal_ns >= COOLDOWN_NS:
            rth, news = in_rth_and_news(tick.ts_ns)
            if rth:
                if news:
                    counts["news_excluded"] += 1
                else:
                    last_signal_ns = tick.ts_ns
                    counts["signals"] += 1
                    d = 1 if flow.signal is Signal.BUY else -1
                    for h in HORIZONS_S:
                        pending[h].append(
                            [tick.ts_ns + h * 1_000_000_000, d, mid,
                             "signal"])
        if n % BASELINE_EVERY == 0:
            rth, news = in_rth_and_news(tick.ts_ns)
            if rth and not news:
                counts["baseline"] += 1
                rng_dir = -rng_dir      # alternating pseudo-random direction
                for h in HORIZONS_S:
                    pending[h].append(
                        [tick.ts_ns + h * 1_000_000_000, rng_dir, mid,
                         "baseline"])
        analyzer.add_trade(tick.price, tick.size, tick.side, "")
        if n % 10_000_000 == 0:
            log.info("… %dM ticks, %d signals so far", n // 1_000_000,
                     counts["signals"])

    log.info("=" * 70)
    log.info("A0 — %s dev set, %d ticks | signals %d (news-excluded %d), "
             "baseline %d", args.product, n, counts["signals"],
             counts["news_excluded"], counts["baseline"])
    passed = False
    table = {}
    for h in HORIZONS_S:
        s_n, s_hit, s_sum = stats[h]["signal"]
        b_n, b_hit, b_sum = stats[h]["baseline"]
        s_rate = s_hit / s_n * 100 if s_n else 0
        b_rate = b_hit / b_n * 100 if b_n else 0
        s_move = s_sum / s_n if s_n else 0
        b_move = b_sum / b_n if b_n else 0
        edge = s_move - b_move
        ok = s_rate >= 53 and edge >= 0.5 and s_n >= 5000
        passed = passed or ok
        table[h] = {"n": s_n, "hit_pct": round(s_rate, 2),
                    "move_ticks": round(s_move, 3),
                    "baseline_hit_pct": round(b_rate, 2),
                    "baseline_move_ticks": round(b_move, 3),
                    "edge_ticks": round(edge, 3), "pass": ok}
        log.info("  +%2ds: n=%6d hit %5.2f%% move %+6.3ft | baseline "
                 "hit %5.2f%% move %+6.3ft | edge %+6.3ft %s",
                 h, s_n, s_rate, s_move, b_rate, b_move, edge,
                 "← PASS" if ok else "")
    verdict = "PASS" if passed else "FAIL (signal_not_predictive)"
    log.info("A0 VERDICT: %s", verdict)

    db = Database(ROOT / config.raw["database"]["path"])
    db.conn.execute(
        "INSERT INTO research_results (strategy, product, phase, trades,"
        " net_profit, flags_json, notes, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        ("order_flow_scalp", args.product, "a0_signal", counts["signals"],
         0.0, json.dumps({"horizons": table, "counts": counts,
                          "news_proxy": "±15min around 08:30/10:00 ET",
                          "cooldown_s": 10}),
         verdict, datetime.now(timezone.utc).isoformat()))
    db.conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
