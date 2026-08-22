"""Databento live feed → engine callbacks (replaces the Tradovate MD socket).

Tradovate refuses md/subscribe* without a CME ILA sub-vendor license
(support confirmed 2026-08-19, docs/API-document.md), so market data comes
from Databento instead: dataset GLBX.MDP3, schemas trades + mbp-1, raw CME
symbols (the resolver's contract code, e.g. MESU6). The Standard plan's
live feed is L1-only — no MBP-10/MBO — so the book holds top-of-book and
OrderFlowAnalyzer must run with book_depth: 1.

Translation (dispatch(), pure and offline-testable):
  MBP1Msg          → book.apply_dom single-level snapshot → on_book_update
                     (its embedded action — including trades — is NOT
                     re-fired; trades arrive on their own subscription)
  TradeMsg         → on_trade(price, size, side) with the NATIVE aggressor
                     side ('B' buy / 'A' sell); side 'N' falls back to the
                     old best-ask inference rule
  SymbolMappingMsg → locks the instrument_id filter for our symbol
  ErrorMsg         → logged; a session that dies having produced no market
                     data after an error is treated as permanent (bad
                     symbol / entitlement — retrying cannot fix it)

Prices are DBN fixed-precision int64 (×1e-9); UNDEF_PRICE marks an empty
side. Disconnects are drop-and-resync exactly like the old MD loop: the
book desyncs and the next session's first MBP-1 record rebuilds it.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

import databento_dbn as dbn
from databento import Live
from databento.common.error import BentoClientError, BentoError

from src.market_data.orderbook import OrderBook
from src.utils.logger import get_logger

log = get_logger(__name__)

UNDEF_PRICE = dbn.UNDEF_PRICE


def _px(raw: int) -> float:
    """DBN int64 (×1e-9) → float. Rounded because the engine compares
    prices against exact tick multiples (raw * 1e-9 leaves epsilon
    artifacts: 7670250000000 * 1e-9 == 7670.250000000001)."""
    return round(raw * 1e-9, 9)


class DatabentoFeed:
    def __init__(self, api_key: str, dataset: str, symbol: str,
                 book: OrderBook,
                 on_book_update: Callable[[], Awaitable[None]],
                 on_trade: Callable[[float, float, str], Awaitable[None]],
                 stall_timeout: float = 30.0):
        self.api_key = api_key
        self.dataset = dataset
        self.symbol = symbol
        self.book = book
        self.on_book_update = on_book_update
        self.on_trade = on_trade
        self.stall_timeout = stall_timeout
        self.instrument_id: int | None = None
        self.md_records = 0          # MBP-1 + trade records actually consumed
        self.error_seen = False

    # ---- translation (no I/O — the offline-testable core) ----

    async def dispatch(self, rec) -> None:
        if isinstance(rec, dbn.SymbolMappingMsg):
            if rec.stype_in_symbol == self.symbol:
                self.instrument_id = rec.instrument_id
                log.info("[%s] mapped to instrument_id=%s",
                         self.symbol, rec.instrument_id)
            return
        if isinstance(rec, dbn.ErrorMsg):
            self.error_seen = True
            log.error("[%s] gateway error: %s", self.symbol,
                      getattr(rec, "err", rec))
            return
        if isinstance(rec, dbn.MBP1Msg):
            if not self._mine(rec):
                return
            self.md_records += 1
            self.book.apply_dom({
                "bids": self._level(rec.bid_px_00, rec.bid_sz_00),
                "asks": self._level(rec.ask_px_00, rec.ask_sz_00),
            })
            await self.on_book_update()
            return
        if isinstance(rec, dbn.TradeMsg):
            if not self._mine(rec):
                return
            self.md_records += 1
            price = _px(rec.price)
            if rec.side == "B":
                side = "buy"
            elif rec.side == "A":
                side = "sell"
            else:                       # 'N' — infer from the book (old rule)
                best_ask = self.book.best_ask()
                side = "buy" if (best_ask and price >= best_ask[0]) else "sell"
            await self.on_trade(price, float(rec.size), side)
        # SystemMsg heartbeats and anything else: ignore

    def _mine(self, rec) -> bool:
        return (self.instrument_id is None
                or rec.instrument_id == self.instrument_id)

    @staticmethod
    def _level(px: int, sz: int) -> list[dict]:
        if px == UNDEF_PRICE or sz <= 0:
            return []                   # empty side → apply_dom leaves book unsynced
        return [{"price": _px(px), "size": sz}]

    # ---- session loop ----

    async def run(self, stop: asyncio.Event) -> int:
        """Reconnecting live session; returns 0 on stop, 3 on a permanent
        subscription problem (bad key / bad symbol / entitlement)."""
        backoff = 1.0
        stop_task = asyncio.create_task(stop.wait(), name="md-stop")
        try:
            while not stop.is_set():
                client = Live(key=self.api_key)
                session_records = self.md_records
                try:
                    for schema in ("trades", "mbp-1"):
                        client.subscribe(dataset=self.dataset, schema=schema,
                                         symbols=[self.symbol],
                                         stype_in="raw_symbol")
                    log.info("MD stream up: %s %s (trades + mbp-1)",
                             self.dataset, self.symbol)
                    backoff = 1.0
                    await self._consume(client, stop_task)
                except BentoClientError as exc:
                    log.error("Databento rejected the session (%s) — check "
                              "DATABENTO_API_KEY / subscription", exc)
                    return 3
                except BentoError as exc:
                    log.warning("Databento session error: %s", exc)
                except asyncio.TimeoutError:
                    log.warning("no records for %.0fs — reconnecting",
                                self.stall_timeout)
                finally:
                    client.stop()
                if self.error_seen and self.md_records == session_records:
                    log.error("session produced no market data after a "
                              "gateway error — subscription problem for %s; "
                              "retrying cannot fix it", self.symbol)
                    return 3
                if not stop.is_set():
                    self.book.desync("Databento session ended")
                    await self._sleep_or_stop(stop, backoff)
                    backoff = min(backoff * 2, 30.0)
            log.info("MD loop stopped")
            return 0
        finally:
            stop_task.cancel()

    async def _consume(self, client: Live, stop_task: asyncio.Task) -> None:
        it = client.__aiter__()
        while not stop_task.done():
            rec_task = asyncio.ensure_future(it.__anext__())
            done, _ = await asyncio.wait(
                {rec_task, stop_task}, timeout=self.stall_timeout,
                return_when=asyncio.FIRST_COMPLETED)
            if rec_task not in done:
                rec_task.cancel()
                if stop_task.done():          # shutdown requested
                    return
                raise asyncio.TimeoutError    # feed stall
            try:
                rec = rec_task.result()
            except StopAsyncIteration:
                log.warning("Databento session closed by gateway")
                return
            await self.dispatch(rec)

    @staticmethod
    async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
