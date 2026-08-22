"""LiveExecutor + UserSyncRouter tests (all offline, fake REST)."""

import asyncio

from src.trading.live_executor import LiveExecutor
from src.trading.user_sync import UserSyncRouter


class FakeREST:
    """Records calls; responses scripted per method name."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def _respond(self, method, default):
        return self.responses.get(method, default)

    async def place_oso(self, **kwargs):
        self.calls.append(("place_oso", kwargs))
        return self._respond("place_oso", {"orderId": 111, "oso1Id": 222})

    async def modify_order(self, order_id, **kwargs):
        self.calls.append(("modify_order", {"order_id": order_id, **kwargs}))
        return self._respond("modify_order", {"commandId": 1})

    async def cancel_order(self, order_id):
        self.calls.append(("cancel_order", {"order_id": order_id}))
        return self._respond("cancel_order", {"commandId": 2})

    async def liquidate_position(self, account_id, contract_id):
        self.calls.append(("liquidate_position",
                           {"account_id": account_id,
                            "contract_id": contract_id}))
        return self._respond("liquidate_position", {"commandId": 3})


def _executor(rest):
    return LiveExecutor(rest, account_spec="DEMO123", account_id=7,
                        contract_id=99, product="MES")


class TestLiveExecutorEnter:
    def test_accepted_entry_tracks_order_ids(self):
        rest = FakeREST()
        ex = _executor(rest)
        sent = asyncio.run(ex.enter("MESU6", "buy", 2, 6400.25, 6390.25))
        assert sent is True
        assert ex.entry_order_id == 111
        assert ex.stop_order_id == 222
        method, body = rest.calls[0]
        assert method == "place_oso"
        assert body["action"] == "Buy"
        assert body["symbol"] == "MESU6"
        assert body["qty"] == 2
        assert body["order_type"] == "Limit"
        assert body["price"] == 6400.25
        assert body["bracket_stop_price"] == 6390.25

    def test_sell_side_maps_to_sell_action(self):
        rest = FakeREST()
        asyncio.run(_executor(rest).enter("MESU6", "sell", 1, 6400.0, 6410.0))
        assert rest.calls[0][1]["action"] == "Sell"

    def test_rejection_returns_false_and_tracks_nothing(self):
        rest = FakeREST({"place_oso": {"failureReason": "AccessDenied",
                                       "failureText": "no trade scope"}})
        ex = _executor(rest)
        assert asyncio.run(ex.enter("MESU6", "buy", 1, 6400.0, 6390.0)) is False
        assert ex.entry_order_id is None
        assert ex.stop_order_id is None

    def test_transport_error_returns_false(self):
        class ExplodingREST(FakeREST):
            async def place_oso(self, **kwargs):
                raise RuntimeError("connection reset")
        ex = _executor(ExplodingREST())
        assert asyncio.run(ex.enter("MESU6", "buy", 1, 6400.0, 6390.0)) is False


class TestLiveExecutorStopAndExit:
    def _entered(self, rest):
        ex = _executor(rest)
        asyncio.run(ex.enter("MESU6", "buy", 2, 6400.25, 6390.25))
        return ex

    def test_modify_stop_targets_bracket_order(self):
        rest = FakeREST()
        ex = self._entered(rest)
        asyncio.run(ex.modify_stop("MESU6", 6395.00))
        method, body = rest.calls[-1]
        assert method == "modify_order"
        assert body["order_id"] == 222
        assert body["order_type"] == "Stop"
        assert body["stop_price"] == 6395.00
        assert body["order_qty"] == 2

    def test_modify_stop_without_tracked_stop_is_noop(self):
        rest = FakeREST()
        asyncio.run(_executor(rest).modify_stop("MESU6", 6395.00))
        assert rest.calls == []

    def test_flatten_cancels_stop_then_liquidates(self):
        rest = FakeREST()
        ex = self._entered(rest)
        asyncio.run(ex.flatten("MESU6", "tp"))
        methods = [m for m, _ in rest.calls[1:]]
        assert methods == ["cancel_order", "liquidate_position"]
        assert rest.calls[1][1]["order_id"] == 222
        assert rest.calls[2][1] == {"account_id": 7, "contract_id": 99}
        assert ex.entry_order_id is None
        assert ex.stop_order_id is None

    def test_cancel_working_cancels_entry_only(self):
        rest = FakeREST()
        ex = self._entered(rest)
        asyncio.run(ex.cancel_working("MESU6", "blackout: CPI"))
        method, body = rest.calls[-1]
        assert method == "cancel_order"
        assert body["order_id"] == 111
        # the protective stop must survive a blackout-start cancel
        assert ex.stop_order_id == 222
        assert ex.entry_order_id is None

    def test_cancel_working_with_no_entry_is_noop(self):
        rest = FakeREST()
        asyncio.run(_executor(rest).cancel_working("MESU6", "session close"))
        assert rest.calls == []


class TestOneBracketGuard:
    """Cap un-acknowledged exposure at one bracket: if fills never arrive
    (unverified user-sync shapes) the bot must not stack entries."""

    def test_second_enter_refused_while_tracked(self):
        rest = FakeREST()
        ex = _executor(rest)
        assert asyncio.run(ex.enter("MESU6", "buy", 2, 6400.0, 6390.0)) is True
        assert asyncio.run(ex.enter("MESU6", "buy", 2, 6401.0, 6391.0)) is False
        assert len([c for c in rest.calls if c[0] == "place_oso"]) == 1

    def test_round_trip_fill_releases_guard(self):
        rest = FakeREST()
        ex = _executor(rest)
        asyncio.run(ex.enter("MESU6", "buy", 2, 6400.0, 6390.0))
        ex.note_fill("buy", 2)           # entry filled
        assert asyncio.run(ex.enter("MESU6", "buy", 1, 6401.0, 6391.0)) is False
        ex.note_fill("sell", 2)          # server-side bracket stop filled
        assert ex.entry_order_id is None and ex.stop_order_id is None
        assert asyncio.run(ex.enter("MESU6", "buy", 1, 6401.0, 6391.0)) is True

    def test_partial_exit_keeps_guard(self):
        rest = FakeREST()
        ex = _executor(rest)
        asyncio.run(ex.enter("MESU6", "buy", 2, 6400.0, 6390.0))
        ex.note_fill("buy", 2)
        ex.note_fill("sell", 1)          # still 1 long — not flat
        assert asyncio.run(ex.enter("MESU6", "buy", 1, 6401.0, 6391.0)) is False

    def test_cancel_working_releases_guard(self):
        rest = FakeREST()
        ex = _executor(rest)
        asyncio.run(ex.enter("MESU6", "buy", 2, 6400.0, 6390.0))
        asyncio.run(ex.cancel_working("MESU6", "session close"))
        assert asyncio.run(ex.enter("MESU6", "buy", 1, 6401.0, 6391.0)) is True

    def test_flatten_releases_guard(self):
        rest = FakeREST()
        ex = _executor(rest)
        asyncio.run(ex.enter("MESU6", "buy", 2, 6400.0, 6390.0))
        asyncio.run(ex.flatten("MESU6", "tp"))
        assert asyncio.run(ex.enter("MESU6", "buy", 1, 6401.0, 6391.0)) is True


class Recorder:
    def __init__(self):
        self.fills = []
        self.nacks = []

    async def on_fill(self, side, qty, price, fee=0.0):
        self.fills.append((side, qty, price))

    async def on_order_nack(self, error=""):
        self.nacks.append(error)


class TestUserSyncRouter:
    def _route(self, msg):
        rec = Recorder()
        router = UserSyncRouter(99, rec.on_fill, rec.on_order_nack)
        asyncio.run(router.route(msg))
        return rec

    def test_fill_created_routes_to_on_fill(self):
        rec = self._route({"e": "props", "d": {
            "entityType": "fill", "eventType": "Created",
            "entity": {"contractId": 99, "action": "Buy",
                       "qty": 2, "price": 6400.25}}})
        assert rec.fills == [("buy", 2, 6400.25)]

    def test_other_contract_fill_ignored(self):
        rec = self._route({"e": "props", "d": {
            "entityType": "fill", "eventType": "Created",
            "entity": {"contractId": 42, "action": "Buy",
                       "qty": 2, "price": 6400.25}}})
        assert rec.fills == []

    def test_malformed_fill_dropped_not_raised(self):
        rec = self._route({"e": "props", "d": {
            "entityType": "fill", "eventType": "Created",
            "entity": {"contractId": 99, "action": "Buy"}}})
        assert rec.fills == []

    def test_rejected_order_routes_to_nack(self):
        rec = self._route({"e": "props", "d": {
            "entityType": "order", "eventType": "Updated",
            "entity": {"id": 111, "ordStatus": "Rejected"}}})
        assert rec.nacks == ["111"]

    def test_non_props_and_md_frames_ignored(self):
        for msg in ({"e": "md", "d": {}}, {"e": "clock"}, {}, "not-a-dict"):
            rec = self._route(msg)
            assert rec.fills == [] and rec.nacks == []


class TestUserSyncRouterDemoFrames:
    """Verbatim frames captured on demo 2026-08-18 (scripts/capture_user_sync.py,
    logs/user_sync_capture_20260818T{014923,020414,021928}Z.jsonl).
    Contract 4399631 (MESU6)."""

    CONTRACT = 4399631

    def _route(self, msg):
        rec = Recorder()
        router = UserSyncRouter(self.CONTRACT, rec.on_fill, rec.on_order_nack)
        asyncio.run(router.route(msg))
        return rec

    def test_real_sell_fill_routes(self):
        rec = self._route({"e": "props", "d": {
            "entityType": "fill", "eventType": "Created",
            "entity": {"id": 601683390105, "orderId": 601683390102,
                       "contractId": 4399631,
                       "timestamp": "2026-08-18T01:50:08.482Z",
                       "tradeDate": {"year": 2026, "month": 8, "day": 18},
                       "action": "Sell", "qty": 1, "price": 7759.75,
                       "active": True, "finallyPaired": 0, "external": False}}})
        assert rec.fills == [("sell", 1, 7759.75)]

    def test_real_buy_fill_routes(self):
        rec = self._route({"e": "props", "d": {
            "entityType": "fill", "eventType": "Created",
            "entity": {"id": 601683390143, "orderId": 601683390111,
                       "contractId": 4399631,
                       "timestamp": "2026-08-18T02:05:26.184Z",
                       "tradeDate": {"year": 2026, "month": 8, "day": 18},
                       "action": "Buy", "qty": 1, "price": 7760.0,
                       "active": True, "finallyPaired": 0, "external": False}}})
        assert rec.fills == [("buy", 1, 7760.0)]

    def test_real_rejected_order_routes_to_nack(self):
        rec = self._route({"e": "props", "d": {
            "entityType": "order", "eventType": "Updated",
            "entity": {"id": 601683390287, "accountId": 60039759,
                       "contractId": 4399631,
                       "timestamp": "2026-08-18T02:20:15.255Z",
                       "action": "Sell", "ordStatus": "Rejected",
                       "archived": False, "external": False, "admin": False}}})
        assert rec.nacks == ["601683390287"] and rec.fills == []

    def test_real_risk_rejected_command_report_dropped(self):
        # Rejection diagnostics arrive separately on commandReport; the nack
        # itself is keyed off the order frame, so this one must only be dropped.
        rec = self._route({"e": "props", "d": {
            "entityType": "commandReport", "eventType": "Created",
            "entity": {"id": 601683390288, "commandId": 601683390287,
                       "timestamp": "2026-08-18T02:20:15.255Z",
                       "commandStatus": "RiskRejected",
                       "rejectReason": "MaxOrderQtyLimitReached",
                       "text": "Your maximum order quantity has been met."}}})
        assert rec.fills == [] and rec.nacks == []

    def test_real_partial_fills_route_individually(self):
        # A 25-lot exit arrived as multiple fill Created frames (2..4 lots
        # each); each must route as its own fill so note_fill sums to flat.
        entities = [
            {"id": 601683390341, "orderId": 601683390331, "contractId": 4399631,
             "timestamp": "2026-08-18T02:20:44.417Z",
             "tradeDate": {"year": 2026, "month": 8, "day": 18},
             "action": "Buy", "qty": 2, "price": 7752.0,
             "active": True, "finallyPaired": 0, "external": False},
            {"id": 601683390343, "orderId": 601683390331, "contractId": 4399631,
             "timestamp": "2026-08-18T02:20:44.417Z",
             "tradeDate": {"year": 2026, "month": 8, "day": 18},
             "action": "Buy", "qty": 4, "price": 7752.0,
             "active": True, "finallyPaired": 0, "external": False},
        ]
        rec = Recorder()
        router = UserSyncRouter(4399631, rec.on_fill, rec.on_order_nack)
        for entity in entities:
            asyncio.run(router.route({"e": "props", "d": {
                "entityType": "fill", "eventType": "Created",
                "entity": entity}}))
        assert rec.fills == [("buy", 2, 7752.0), ("buy", 4, 7752.0)]

    def test_real_canceled_order_is_not_a_nack(self):
        rec = self._route({"e": "props", "d": {
            "entityType": "order", "eventType": "Updated",
            "entity": {"id": 601683390113, "accountId": 60039759,
                       "contractId": 4399631,
                       "timestamp": "2026-08-18T01:50:08.485Z",
                       "action": "Buy", "ordStatus": "Canceled",
                       "executionProviderId": 1, "archived": False,
                       "external": False, "admin": False}}})
        assert rec.fills == [] and rec.nacks == []

    def test_real_suspended_bracket_leg_dropped(self):
        rec = self._route({"e": "props", "d": {
            "entityType": "order", "eventType": "Updated",
            "entity": {"id": 601683390111, "accountId": 60039759,
                       "contractId": 4399631,
                       "timestamp": "2026-08-18T01:50:08.485Z",
                       "action": "Buy", "ordStatus": "Suspended",
                       "archived": False, "external": False, "admin": False}}})
        assert rec.fills == [] and rec.nacks == []

    def test_real_execution_report_and_strategy_frames_dropped(self):
        frames = [
            {"e": "props", "d": {
                "entityType": "executionReport", "eventType": "Created",
                "entity": {"id": 601683390152, "commandId": 601683390151,
                           "name": "0.21674477858923083", "accountId": 60039759,
                           "contractId": 4399631,
                           "timestamp": "2026-08-18T02:05:26.189Z",
                           "orderId": 601683390113, "execType": "Canceled",
                           "ordStatus": "Canceled", "action": "Buy",
                           "externalClOrdId": "1.4730722956780502"}}},
            {"e": "props", "d": {
                "entityType": "orderStrategy", "eventType": "Created",
                "entity": {"id": 601683390101, "accountId": 60039759,
                           "timestamp": "2026-08-18T01:50:08.477Z",
                           "contractId": 4399631, "orderStrategyTypeId": 2,
                           "action": "Sell",
                           "status": "InactiveStrategy", "archived": False,
                           "senderId": 8575111, "userSessionId": 3051973041}}},
        ]
        for msg in frames:
            rec = self._route(msg)
            assert rec.fills == [] and rec.nacks == []
