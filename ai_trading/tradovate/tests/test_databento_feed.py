"""DatabentoFeed translation tests (all offline, real DBN record objects)."""

import asyncio

import databento_dbn as dbn

from src.market_data.databento_feed import DatabentoFeed
from src.market_data.orderbook import OrderBook

PX = 1_000_000_000  # DBN fixed-precision scale


def _trade(price: float, size: int, side: dbn.Side, iid: int = 42) -> dbn.TradeMsg:
    return dbn.TradeMsg(1, iid, 0, int(price * PX), size,
                        dbn.Action.TRADE, side, 0, 0)


def _mbp1(bid: float, bid_sz: int, ask: float, ask_sz: int,
          iid: int = 42) -> dbn.MBP1Msg:
    return dbn.MBP1Msg(1, iid, 0, int(bid * PX), bid_sz,
                       dbn.Action.MODIFY, dbn.Side.BID, 0, 0,
                       levels=dbn.BidAskPair(
                           int(bid * PX), int(ask * PX), bid_sz, ask_sz, 1, 1))


def _mapping(symbol: str, iid: int) -> dbn.SymbolMappingMsg:
    return dbn.SymbolMappingMsg(1, iid, 0, dbn.SType.RAW_SYMBOL, symbol,
                                dbn.SType.RAW_SYMBOL, symbol, 0, 0)


class Recorder:
    def __init__(self):
        self.book_updates = 0
        self.trades = []

    async def on_book_update(self):
        self.book_updates += 1

    async def on_trade(self, price, size, side):
        self.trades.append((price, size, side))


def _feed():
    rec = Recorder()
    book = OrderBook("MESU6", 0.25)
    feed = DatabentoFeed(api_key="db-test", dataset="GLBX.MDP3",
                         symbol="MESU6", book=book,
                         on_book_update=rec.on_book_update,
                         on_trade=rec.on_trade)
    return feed, book, rec


class TestBookTranslation:
    def test_mbp1_syncs_book_with_scaled_prices(self):
        feed, book, rec = _feed()
        asyncio.run(feed.dispatch(_mbp1(6400.00, 5, 6400.25, 3)))
        assert book.synced
        assert book.best_bid() == (6400.00, 5)
        assert book.best_ask() == (6400.25, 3)
        assert rec.book_updates == 1

    def test_undef_price_side_leaves_book_unsynced(self):
        feed, book, rec = _feed()
        raw = dbn.MBP1Msg(1, 42, 0, int(6400 * PX), 5,
                          dbn.Action.MODIFY, dbn.Side.BID, 0, 0,
                          levels=dbn.BidAskPair(
                              int(6400 * PX), dbn.UNDEF_PRICE, 5, 0, 1, 0))
        asyncio.run(feed.dispatch(raw))
        assert not book.synced
        assert rec.book_updates == 1  # update still fires; queries return None

    def test_mbp1_embedded_trade_action_does_not_fire_on_trade(self):
        feed, book, rec = _feed()
        raw = dbn.MBP1Msg(1, 42, 0, int(6400.25 * PX), 2,
                          dbn.Action.TRADE, dbn.Side.ASK, 0, 0,
                          levels=dbn.BidAskPair(
                              int(6400 * PX), int(6400.25 * PX), 5, 3, 1, 1))
        asyncio.run(feed.dispatch(raw))
        assert rec.trades == []
        assert rec.book_updates == 1


class TestTradeTranslation:
    def test_prices_are_exact_tick_multiples(self):
        # 7670250000000 * 1e-9 == 7670.250000000001 unrounded — caught live
        feed, book, rec = _feed()
        asyncio.run(feed.dispatch(_mbp1(7669.75, 21, 7670.00, 20)))
        asyncio.run(feed.dispatch(_trade(7670.25, 1, dbn.Side.ASK)))
        assert book.best_bid() == (7669.75, 21)
        assert book.best_ask() == (7670.00, 20)
        assert rec.trades == [(7670.25, 1.0, "sell")]

    def test_native_aggressor_sides(self):
        feed, book, rec = _feed()
        asyncio.run(feed.dispatch(_trade(6400.25, 2, dbn.Side.BID)))
        asyncio.run(feed.dispatch(_trade(6400.00, 1, dbn.Side.ASK)))
        assert rec.trades == [(6400.25, 2.0, "buy"), (6400.00, 1.0, "sell")]

    def test_side_none_falls_back_to_best_ask_rule(self):
        feed, book, rec = _feed()
        asyncio.run(feed.dispatch(_mbp1(6400.00, 5, 6400.25, 3)))
        asyncio.run(feed.dispatch(_trade(6400.25, 1, dbn.Side.NONE)))  # at ask
        asyncio.run(feed.dispatch(_trade(6400.00, 1, dbn.Side.NONE)))  # at bid
        assert [t[2] for t in rec.trades] == ["buy", "sell"]

    def test_side_none_with_unsynced_book_defaults_to_sell(self):
        feed, book, rec = _feed()
        asyncio.run(feed.dispatch(_trade(6400.25, 1, dbn.Side.NONE)))
        assert rec.trades == [(6400.25, 1.0, "sell")]


class TestInstrumentFilter:
    def test_mapping_locks_instrument_and_filters_others(self):
        feed, book, rec = _feed()
        asyncio.run(feed.dispatch(_mapping("MESU6", 42)))
        assert feed.instrument_id == 42
        asyncio.run(feed.dispatch(_trade(6400.25, 1, dbn.Side.BID, iid=99)))
        assert rec.trades == []
        asyncio.run(feed.dispatch(_trade(6400.25, 1, dbn.Side.BID, iid=42)))
        assert len(rec.trades) == 1

    def test_mapping_for_other_symbol_is_ignored(self):
        feed, book, rec = _feed()
        asyncio.run(feed.dispatch(_mapping("MNQU6", 7)))
        assert feed.instrument_id is None

    def test_unmapped_feed_accepts_all(self):
        feed, book, rec = _feed()
        asyncio.run(feed.dispatch(_trade(6400.25, 1, dbn.Side.BID, iid=1)))
        assert len(rec.trades) == 1


class TestErrorHandling:
    def test_error_record_sets_flag_without_callbacks(self):
        feed, book, rec = _feed()
        err = dbn.ErrorMsg(0, "Failed to resolve symbols")
        asyncio.run(feed.dispatch(err))
        assert feed.error_seen
        assert rec.trades == [] and rec.book_updates == 0

    def test_md_record_counter_tracks_consumed_data(self):
        feed, book, rec = _feed()
        asyncio.run(feed.dispatch(_mbp1(6400.00, 5, 6400.25, 3)))
        asyncio.run(feed.dispatch(_trade(6400.25, 1, dbn.Side.BID)))
        assert feed.md_records == 2
