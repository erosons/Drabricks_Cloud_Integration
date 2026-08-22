"""Pessimistic bar-level bracket simulator for the card strategies (§9).

The tick backtester (backtester.py) serves the tick-native order_flow
engine; this simulator serves the 22 playbook-card strategies, which are
bar-mechanical by design. Same honesty rules, translated to bars:

  * market entries/exits fill at the NEXT bar's open, slippage against
  * stop entries need the bar to trade THROUGH the trigger (high > trigger
    for buys), filling at max(open, trigger) plus slippage
  * limit fills need penetration (bar low < limit for buys) and never
    price-improve; a touch is not a fill
  * protective stops fill at min(open, stop) − slippage (longs; mirrored)
  * when stop and target are both inside one bar, THE STOP FIRES —
    worst-case intrabar ordering, always
  * a target can never fill on the entry bar (no same-bar entry+exit)
  * close-based exits (trail flips, EMA touch rules, time stops) are
    evaluated on the closed bar and fill at the next bar's open
  * hard flatten at (session close − buffer); no entries outside RTH
  * commissions per side per contract on every fill

One position, flat between trades — matching the live one-bracket guard.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.utils.logger import get_logger

log = get_logger("bar_backtester")


@dataclass
class Entry:
    """What a card strategy asks for on a closed bar (flat only)."""
    side: str                    # "buy" / "sell"
    kind: str                    # "market" | "stop" | "limit"
    trigger: float | None        # stop/limit price (None for market)
    stop: float                  # protective stop
    target: float | None = None  # bracket limit target (None = rule exit)
    time_stop_bars: int | None = None
    ttl_bars: int = 12           # unfilled working entry expires
    tag: str = ""


@dataclass
class Position:
    side: str
    qty: int
    entry_price: float
    entry_ts: str
    stop: float
    target: float | None
    time_stop_bars: int | None
    bars_held: int = 0
    tag: str = ""


@dataclass
class BarTrade:
    side: str
    qty: int
    entry_ts: str
    entry_price: float
    exit_ts: str
    exit_price: float
    exit_reason: str
    fees: float
    pnl_usd: float
    tag: str = ""


@dataclass
class BarRunResult:
    strategy: str
    product: str
    timeframe_min: int
    date_from: str
    date_to: str
    bars: int
    trades: list[BarTrade] = field(default_factory=list)
    flags: dict = field(default_factory=dict)

    def stats(self) -> dict:
        closed = self.trades
        wins = [t for t in closed if t.pnl_usd >= 0]
        losses = [t for t in closed if t.pnl_usd < 0]
        gross_win = sum(t.pnl_usd for t in wins)
        gross_loss = -sum(t.pnl_usd for t in losses)
        equity, peak, max_dd = 0.0, 0.0, 0.0
        for t in closed:
            equity += t.pnl_usd
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        return {
            "trades": len(closed), "wins": len(wins), "losses": len(losses),
            "win_rate": len(wins) / len(closed) if closed else 0.0,
            "net_profit": sum(t.pnl_usd for t in closed),
            "fees": sum(t.fees for t in closed),
            "profit_factor": (gross_win / gross_loss if gross_loss
                              else float("inf") if gross_win else 0.0),
            "max_drawdown": max_dd,
            "largest_loss": min((t.pnl_usd for t in closed), default=0.0),
        }


class BarBracketSim:
    def __init__(self, strategy, product, df: pd.DataFrame,
                 slippage_ticks: int = 2, commission_per_side: float = 1.10):
        self.strategy = strategy
        self.product = product
        self.df = df
        self.tick = product.tick_size
        self.usd_per_point = product.tick_value / product.tick_size
        self.slip = slippage_ticks * product.tick_size
        self.commission = commission_per_side
        self.qty = product.risk.max_contracts
        self.max_risk_usd = product.risk.stop_loss_usd

    def run(self) -> BarRunResult:
        df = self.df
        strategy = self.strategy
        trades: list[BarTrade] = []
        flags = {"entries": 0, "entry_expired": 0, "skipped_wide_stop": 0,
                 "stop_and_target_same_bar": 0, "news_guard": "PERMISSIVE"}
        pos: Position | None = None
        working: Entry | None = None
        working_age = 0
        pending_market: Entry | None = None      # fills at this bar's open
        pending_exit: str | None = None          # rule exit at this bar's open

        opens = df["open"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        in_session = df["in_session"].to_numpy()
        flatten = df["flatten"].to_numpy()
        index = df.index

        def close_pos(i: int, price: float, reason: str) -> None:
            nonlocal pos
            points = ((price - pos.entry_price) if pos.side == "buy"
                      else (pos.entry_price - price))
            fees = 2 * pos.qty * self.commission
            trades.append(BarTrade(
                side=pos.side, qty=pos.qty, entry_ts=pos.entry_ts,
                entry_price=pos.entry_price, exit_ts=str(index[i]),
                exit_price=price, exit_reason=reason, fees=fees,
                pnl_usd=points * pos.qty * self.usd_per_point - fees,
                tag=pos.tag))
            pos = None

        for i in range(len(df)):
            o, h, lo = opens[i], highs[i], lows[i]

            # ---- exits queued from the prior closed bar ----
            if pos is not None and pending_exit is not None:
                adverse = -self.slip if pos.side == "buy" else self.slip
                close_pos(i, o + adverse, pending_exit)
            pending_exit = None

            # ---- market entry queued from the prior closed bar ----
            if pending_market is not None and pos is None and in_session[i] \
                    and not flatten[i]:
                e = pending_market
                adverse = self.slip if e.side == "buy" else -self.slip
                pos = Position(e.side, self.qty, o + adverse, str(index[i]),
                               e.stop, e.target, e.time_stop_bars, tag=e.tag)
                flags["entries"] += 1
            pending_market = None

            # ---- working stop/limit entry against this bar ----
            if working is not None:
                if flatten[i] or not in_session[i]:
                    working = None
                else:
                    working_age += 1
                    fill = None
                    e = working
                    if e.kind == "stop":
                        if e.side == "buy" and h > e.trigger:
                            fill = max(o, e.trigger) + self.slip
                        elif e.side == "sell" and lo < e.trigger:
                            fill = min(o, e.trigger) - self.slip
                    else:  # limit — penetration only, no improvement
                        if e.side == "buy" and lo < e.trigger:
                            fill = e.trigger
                        elif e.side == "sell" and h > e.trigger:
                            fill = e.trigger
                    if fill is not None:
                        pos = Position(e.side, self.qty, fill, str(index[i]),
                                       e.stop, e.target, e.time_stop_bars,
                                       tag=e.tag)
                        flags["entries"] += 1
                        working = None
                        # entry bar: protective stop may still fire (below);
                        # the target may NOT (no same-bar entry+exit)
                        if pos.side == "buy" and lo <= pos.stop:
                            close_pos(i, min(o, pos.stop) - self.slip, "stop")
                        elif pos.side == "sell" and h >= pos.stop:
                            close_pos(i, max(o, pos.stop) + self.slip, "stop")
                        if pos is None:
                            continue
                    elif working_age >= e.ttl_bars:
                        working = None
                        flags["entry_expired"] += 1

            # ---- manage an open position against this bar ----
            elif pos is not None:
                pos.bars_held += 1
                stop_hit = (lo <= pos.stop if pos.side == "buy"
                            else h >= pos.stop)
                tgt_hit = (pos.target is not None
                           and (h > pos.target if pos.side == "buy"
                                else lo < pos.target))
                if stop_hit and tgt_hit:
                    flags["stop_and_target_same_bar"] += 1
                if stop_hit:                       # pessimistic: stop first
                    px = (min(o, pos.stop) - self.slip if pos.side == "buy"
                          else max(o, pos.stop) + self.slip)
                    close_pos(i, px, "stop")
                elif tgt_hit:
                    close_pos(i, pos.target, "target")
                elif flatten[i]:
                    adverse = -self.slip if pos.side == "buy" else self.slip
                    close_pos(i, o + adverse, "session_flatten")
                elif (pos.time_stop_bars is not None
                        and pos.bars_held >= pos.time_stop_bars):
                    pending_exit = "time_stop"
                else:
                    # card-specific close-based management on the closed bar
                    action = strategy.manage(self.df, i, pos)
                    if action == "exit":
                        pending_exit = "rule_exit"
                    elif isinstance(action, (int, float)):
                        # trail update — ratchet only, never loosens
                        if pos.side == "buy":
                            pos.stop = max(pos.stop, float(action))
                        else:
                            pos.stop = min(pos.stop, float(action))

            # ---- new signal on this closed bar (flat, in session) ----
            if pos is None and working is None and pending_market is None \
                    and in_session[i] and not flatten[i]:
                entry = strategy.on_bar(self.df, i)
                if entry is not None:
                    risk_pts = abs((entry.trigger if entry.kind != "market"
                                    else opens[min(i + 1, len(df) - 1)])
                                   - entry.stop)
                    if risk_pts * self.usd_per_point * self.qty \
                            > self.max_risk_usd:
                        flags["skipped_wide_stop"] += 1
                    elif entry.kind == "market":
                        pending_market = entry
                    else:
                        working = entry
                        working_age = 0

        if pos is not None:                        # end of data
            close_pos(len(df) - 1, opens[-1], "end_of_data")
            flags["forced_final_exit"] = True

        return BarRunResult(
            strategy=strategy.name, product=self.product.symbol,
            timeframe_min=strategy.timeframe_min,
            date_from=str(index[0])[:10], date_to=str(index[-1])[:10],
            bars=len(df), trades=trades, flags=flags)
