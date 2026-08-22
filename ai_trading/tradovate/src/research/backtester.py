"""Event-driven tick backtester (§9) — one code path with live.

Replays TBBO history (tick trades + BBO, Databento GLBX.MDP3) through the
SAME FuturesOrderFlowStrategy, RiskManager, SessionManager, and OrderBook
the live bot runs. Only the executor differs: PessimisticBracketExecutor
simulates the OSO bracket under the book's backtest-honesty rules.

Pessimistic fill model (non-configurable floor, §9):
  * limit entries fill only when price trades THROUGH the limit — a touch
    is never a fill (touches are counted in fill_flags instead)
  * protective stops fill at the stop or the triggering trade price,
    whichever is worse, minus `slippage_ticks` more against the position
  * every non-stop exit (TP, blackout/session flatten) is a market order
    that fills on the NEXT tick at that tick's price, slippage against
  * commissions are charged per side per contract on every fill

Sim time: tick timestamps drive both engine clocks — now_fn (session /
news gates, ET-aware) and clock_fn (order cooldown, NACK pause) — so a
year replays in minutes while cooldowns elapse in market time.

The news guard is PERMISSIVE by default (no historical red-folder
calendar exists in the DB for the replay window); this is recorded
loudly in fill_flags so no run can silently claim news-gated results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, NamedTuple

from src.config_loader import AppConfig
from src.market_data.orderbook import OrderBook
from src.scheduling.session_manager import SessionManager
from src.storage.db import Database
from src.trading.order_flow import (
    FuturesOrderFlowStrategy,
    OrderFlowAnalyzer,
)
from src.trading.position import PositionTracker
from src.trading.price_action import PriceActionAnalyzer
from src.trading.risk import RiskManager
from src.utils.logger import get_logger

log = get_logger("backtester")


class Tick(NamedTuple):
    ts_ns: int          # event time, epoch nanoseconds (UTC)
    price: float        # trade price
    size: float
    side: str           # "buy" / "sell" aggressor
    bid: float
    ask: float
    bid_sz: int
    ask_sz: int


@dataclass
class SimTrade:
    side: str
    qty: int
    entry_ts: str
    entry_price: float
    exit_ts: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    fees: float = 0.0
    pnl_usd: float = 0.0    # net of fees


class _PermissiveNews:
    def entering_blackout(self, prev, now):
        return None

    def active_blackout(self, now):
        return None


class PessimisticBracketExecutor:
    """Executor-protocol OSO bracket simulator; fills via `on_tick`."""

    def __init__(self, product, on_fill, slippage_ticks: int = 2,
                 commission_per_side: float = 1.10):
        self.product = product
        self.tick_size = product.tick_size
        self.usd_per_point = product.tick_value / product.tick_size
        self.on_fill = on_fill              # async (side, qty, price, fee)
        self.slippage = slippage_ticks * product.tick_size
        self.commission = commission_per_side

        self.entry: dict | None = None      # resting limit + attached stop
        self.stop: dict | None = None       # active protective stop
        self.market_exit: str | None = None # exit reason pending next tick
        self.pos_qty = 0                    # signed, executor's own view
        self.trades: list[SimTrade] = []
        self._open: SimTrade | None = None
        self.flags = {"touch_no_fill": 0, "entries_refused_busy": 0,
                      "stop_fills": 0, "market_exit_fills": 0}
        self._now: datetime | None = None

    @property
    def _now_iso(self) -> str:
        return self._now.isoformat() if self._now else ""

    # ---- Executor protocol ----

    async def enter(self, symbol, side, qty, limit_price, bracket_stop) -> bool:
        if self.entry is not None or self.pos_qty != 0:
            self.flags["entries_refused_busy"] += 1
            return False
        self.entry = {"side": side, "qty": qty, "limit": limit_price,
                      "stop": bracket_stop}
        return True

    async def modify_stop(self, symbol, new_stop) -> None:
        if self.stop is not None:
            self.stop["price"] = new_stop

    async def flatten(self, symbol, reason) -> None:
        if self.pos_qty == 0:
            return
        self.stop = None                    # bracket cancelled with the exit
        self.market_exit = reason           # fills on the NEXT tick

    async def cancel_working(self, symbol, reason) -> None:
        # entry leg only — the protective stop survives (LiveExecutor parity)
        self.entry = None

    # ---- simulation ----

    async def on_tick(self, tick: Tick, now: datetime) -> None:
        """Process resting orders against one trade BEFORE the engine sees
        it (the exchange is upstream of the bot)."""
        self._now = now          # iso-formatted lazily, only on fills
        if self.market_exit is not None:
            await self._fill_market_exit(tick)
        if self.stop is not None:
            await self._check_stop(tick)
        if self.entry is not None:
            await self._check_entry(tick)

    async def _check_entry(self, tick: Tick) -> None:
        e = self.entry
        if e["side"] == "buy":
            through = tick.price < e["limit"]
            touch = tick.price == e["limit"]
        else:
            through = tick.price > e["limit"]
            touch = tick.price == e["limit"]
        if touch:
            self.flags["touch_no_fill"] += 1
        if not through:
            return
        self.entry = None
        qty, side, px = e["qty"], e["side"], e["limit"]
        self.pos_qty = qty if side == "buy" else -qty
        self.stop = {"price": e["stop"]}
        self._open = SimTrade(side=side, qty=qty, entry_ts=self._now_iso,
                              entry_price=px)
        await self._emit(side, qty, px)

    async def _check_stop(self, tick: Tick) -> None:
        s = self.stop["price"]
        if self.pos_qty > 0 and tick.price <= s:
            fill = min(tick.price, s) - self.slippage
        elif self.pos_qty < 0 and tick.price >= s:
            fill = max(tick.price, s) + self.slippage
        else:
            return
        self.flags["stop_fills"] += 1
        await self._close(fill, "stop")

    async def _fill_market_exit(self, tick: Tick) -> None:
        reason = self.market_exit
        self.market_exit = None
        if self.pos_qty == 0:
            return
        adverse = -self.slippage if self.pos_qty > 0 else self.slippage
        self.flags["market_exit_fills"] += 1
        await self._close(tick.price + adverse, reason)

    async def force_close(self, price: float, reason: str) -> None:
        """End of data with a position still open — close at the last
        price, slippage against, and flag it."""
        self.entry = None
        self.stop = None
        if self.pos_qty != 0:
            adverse = -self.slippage if self.pos_qty > 0 else self.slippage
            await self._close(price + adverse, reason)

    async def _close(self, fill_price: float, reason: str) -> None:
        qty = abs(self.pos_qty)
        exit_side = "sell" if self.pos_qty > 0 else "buy"
        self.stop = None
        self.pos_qty = 0
        t = self._open
        if t is not None:
            t.exit_ts = self._now_iso
            t.exit_price = fill_price
            t.exit_reason = reason
            points = ((fill_price - t.entry_price) if t.side == "buy"
                      else (t.entry_price - fill_price))
            t.fees = 2 * qty * self.commission
            t.pnl_usd = points * qty * self.usd_per_point - t.fees
            self.trades.append(t)
            self._open = None
        await self._emit(exit_side, qty, fill_price)

    async def _emit(self, side: str, qty: int, price: float) -> None:
        await self.on_fill(side, qty, price, qty * self.commission)


@dataclass
class BacktestResult:
    product: str
    date_from: str
    date_to: str
    ticks: int
    trades: list[SimTrade]
    skips: dict
    fill_flags: dict
    params: dict = field(default_factory=dict)

    @property
    def closed(self) -> list[SimTrade]:
        return [t for t in self.trades if t.exit_reason]

    def stats(self) -> dict:
        closed = self.closed
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
            "trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(closed) if closed else 0.0,
            "net_profit": sum(t.pnl_usd for t in closed),
            "fees": sum(t.fees for t in closed),
            "profit_factor": (gross_win / gross_loss if gross_loss
                              else float("inf") if gross_win else 0.0),
            "max_drawdown": max_dd,
            "largest_loss": min((t.pnl_usd for t in closed), default=0.0),
        }

    def persist(self, db: Database, strategy: str = "order_flow_scalp",
                kind: str = "limited") -> int:
        s = self.stats()
        cur = db.conn.execute(
            "INSERT INTO backtest_runs (strategy, product, kind, params_json,"
            " date_from, date_to, net_profit, max_drawdown, trades,"
            " largest_loss, fill_flags_json, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (strategy, self.product, kind, json.dumps(self.params),
             self.date_from, self.date_to, s["net_profit"], s["max_drawdown"],
             s["trades"], s["largest_loss"], json.dumps(self.fill_flags),
             datetime.now(timezone.utc).isoformat()))
        db.conn.commit()
        return cur.lastrowid


class Backtester:
    """Wires the live engine to the sim executor and replays ticks."""

    def __init__(self, config: AppConfig, product_symbol: str,
                 slippage_ticks: int = 2, commission_per_side: float = 1.10,
                 news_guard=None):
        product = config.products[product_symbol]
        params = config.strategies["order_flow_scalp"].params
        self._now = datetime.now(timezone.utc)

        positions = PositionTracker(product.tick_size, product.tick_value)
        self.executor = PessimisticBracketExecutor(
            product, self._on_fill, slippage_ticks, commission_per_side)
        self.engine = FuturesOrderFlowStrategy(
            product=product,
            contract_symbol=f"{product_symbol}.SIM",
            analyzer=OrderFlowAnalyzer(
                imbalance_threshold=params["imbalance_threshold"],
                book_depth=params["book_depth"],
                min_confidence=params["min_confidence"]),
            price_action=PriceActionAnalyzer(
                fast_period=params["fast_ema"],
                slow_period=params["slow_ema"],
                spike_threshold=params["spike_threshold"],
                recovery_pct=params["recovery_pct"],
                exhaustion_ttl=params["exhaustion_ttl"],
                retest_proximity=params["retest_proximity"],
                retest_memory_ticks=params["retest_memory_ticks"],
                retest_ttl=params["retest_ttl"]),
            risk_manager=RiskManager(product),
            position_tracker=positions,
            executor=self.executor,
            session_manager=SessionManager(config.raw["session"]),
            news_guard=news_guard or _PermissiveNews(),
            max_spread_ticks=params["max_spread_ticks"],
            now_fn=lambda: self._now,
            clock_fn=lambda: self._now.timestamp())
        self.engine.attach_orderbook(
            OrderBook(f"{product_symbol}.SIM", product.tick_size))
        self.product_symbol = product_symbol
        self.params = {"slippage_ticks": slippage_ticks,
                       "commission_per_side": commission_per_side,
                       **{k: params[k] for k in
                          ("book_depth", "imbalance_threshold",
                           "min_confidence", "max_spread_ticks")}}
        if news_guard is None:
            log.warning("news guard PERMISSIVE — no historical calendar; "
                        "recorded in fill_flags")

    async def _on_fill(self, side, qty, price, fee) -> None:
        await self.engine.on_fill(side, qty, price, fee)

    async def run(self, ticks: Iterable[Tick],
                  progress_every: int = 5_000_000) -> BacktestResult:
        engine, executor = self.engine, self.executor
        book = engine.book
        n, first_iso, last_price = 0, "", 0.0
        for tick in ticks:
            now = datetime.fromtimestamp(tick.ts_ns / 1e9, tz=timezone.utc)
            self._now = now
            if not first_iso:
                first_iso = now.isoformat()
            last_price = tick.price
            await executor.on_tick(tick, now)
            book.apply_dom({
                "bids": [{"price": tick.bid, "size": tick.bid_sz}],
                "asks": [{"price": tick.ask, "size": tick.ask_sz}]})
            await engine.on_book_update()
            await engine.on_trade(tick.price, tick.size, tick.side)
            n += 1
            if progress_every and n % progress_every == 0:
                log.info("replayed %dM ticks (%s) — %d trades so far",
                         n // 1_000_000, now.date(), len(executor.trades))
        forced = executor.pos_qty != 0
        if forced:
            await executor.force_close(last_price, "end_of_data")
        flags = dict(executor.flags)
        flags["forced_final_exit"] = forced
        flags["news_guard"] = "historical" if not isinstance(
            engine.news, _PermissiveNews) else "PERMISSIVE (no calendar)"
        return BacktestResult(
            product=self.product_symbol,
            date_from=first_iso[:10], date_to=self._now.isoformat()[:10],
            ticks=n, trades=executor.trades, skips=dict(engine.skips),
            fill_flags=flags, params=self.params)


def load_tbbo_dir(data_dir: str | Path, date_from: str | None = None,
                  date_to: str | None = None,
                  chunk_rows: int = 2_000_000) -> Iterator[Tick]:
    """Stream Ticks from a Databento batch-job directory of monthly
    *.tbbo.dbn.zst files, in time order. Dates are inclusive YYYY-MM-DD."""
    import databento as dbn_client

    files = sorted(Path(data_dir).glob("*.tbbo.dbn.zst"))
    if not files:
        raise FileNotFoundError(f"no *.tbbo.dbn.zst under {data_dir}")
    lo = (int(datetime.fromisoformat(f"{date_from}T00:00:00+00:00")
              .timestamp() * 1e9) if date_from else 0)
    hi = (int(datetime.fromisoformat(f"{date_to}T23:59:59+00:00")
              .timestamp() * 1e9 + 1e9) if date_to else 2**63 - 1)
    for f in files:
        # file names carry the range: glbx-mdp3-YYYYMMDD-YYYYMMDD.tbbo.dbn.zst
        span = f.stem.split(".")[0].split("-")
        f_from = f"{span[2][:4]}-{span[2][4:6]}-{span[2][6:]}"
        f_to = f"{span[3][:4]}-{span[3][4:6]}-{span[3][6:]}"
        if (date_to and f_from > date_to) or (date_from and f_to < date_from):
            continue
        log.info("loading %s", f.name)
        store = dbn_client.DBNStore.from_file(f)
        for df in store.to_df(count=chunk_rows):
            df = df.reset_index()
            ts = df["ts_recv"].astype("int64")
            keep = (df["side"] != "N") & (ts >= lo) & (ts < hi)
            for row in zip(ts[keep], df["price"][keep], df["size"][keep],
                           df["side"][keep], df["bid_px_00"][keep],
                           df["ask_px_00"][keep], df["bid_sz_00"][keep],
                           df["ask_sz_00"][keep]):
                yield Tick(int(row[0]), float(row[1]), float(row[2]),
                           "buy" if row[3] == "B" else "sell",
                           float(row[4]), float(row[5]),
                           int(row[6]), int(row[7]))
