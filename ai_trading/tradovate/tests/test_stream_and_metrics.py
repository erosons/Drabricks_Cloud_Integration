import asyncio

from src.market_data.orderbook import OrderBook
from src.market_data.stream import MdRouter
from src.utils.metrics import BotMetrics


def _router(contract_id=101):
    book = OrderBook("YMU6", tick_size=1.0)
    events = {"book": 0, "trades": []}

    async def on_book():
        events["book"] += 1

    async def on_trade(price, size, side):
        events["trades"].append((price, size, side))

    return MdRouter(book, contract_id, on_book, on_trade), book, events


DOM_MSG = {"e": "md", "d": {"doms": [{
    "contractId": 101,
    "bids": [{"price": 40_000, "size": 20}],
    "asks": [{"price": 40_001, "size": 15}],
}]}}


class TestMdRouter:
    def test_dom_updates_book_and_fires_callback(self):
        router, book, events = _router()
        asyncio.run(router.route(DOM_MSG))
        assert events["book"] == 1
        assert book.best_bid() == (40_000, 20)

    def test_other_contract_ignored(self):
        router, book, events = _router(contract_id=999)
        asyncio.run(router.route(DOM_MSG))
        assert events["book"] == 0
        assert not book.synced

    def test_trade_quote_side_inferred_from_book(self):
        router, book, events = _router()

        async def scenario():
            await router.route(DOM_MSG)
            await router.route({"e": "md", "d": {"quotes": [{
                "contractId": 101,
                "entries": {"Trade": {"price": 40_001, "size": 3}}}]}})
            await router.route({"e": "md", "d": {"quotes": [{
                "contractId": 101,
                "entries": {"Trade": {"price": 40_000, "size": 2}}}]}})
        asyncio.run(scenario())
        assert events["trades"] == [(40_001.0, 3.0, "buy"),
                                    (40_000.0, 2.0, "sell")]

    def test_non_md_and_malformed_ignored(self):
        router, _, events = _router()

        async def scenario():
            await router.route({"e": "props", "d": {}})
            await router.route({"i": 5, "s": 200})
            await router.route({"e": "md", "d": {"quotes": [{
                "contractId": 101, "entries": {}}]}})
        asyncio.run(scenario())
        assert events == {"book": 0, "trades": []}


class TestMetrics:
    def test_full_interface_smoke(self):
        m = BotMetrics("YMTEST")
        m.update_emas(1.0, 2.0, 3.0)
        m.update_pnl(10.0, -5.0)
        m.update_position(1, 39_900.0, 40_300.0)
        m.update_signal("buy")
        m.update_signal("neutral")
        m.inc_orders_placed()
        m.inc_orders_filled()
        m.inc_sl_hit()
        m.inc_tp_hit()
