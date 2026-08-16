"""Offline tests for the Tradovate client layer: frame codec, auth parsing,
rate bucket, penalty persistence, gateway retry flow, order body building."""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.auth.tradovate_auth import (
    AuthError,
    Credentials,
    PenaltyResponse,
    parse_penalty,
    parse_token_response,
)
from src.client.gateway import PenaltyStore, TokenBucket
from src.client.rest import TradovateREST
from src.client.websocket import Frame, ProtocolError, encode_request, parse_frame


class TestFrameCodec:
    def test_control_frames(self):
        assert parse_frame("o") == Frame("o")
        assert parse_frame("h") == Frame("h")
        assert parse_frame("c") == Frame("c")

    def test_data_frame_batches_messages(self):
        raw = 'a[{"i":1,"s":200,"d":{"ok":true}},{"e":"md","d":{"quotes":[]}}]'
        frame = parse_frame(raw)
        assert frame.kind == "a"
        assert len(frame.messages) == 2
        assert frame.messages[0]["i"] == 1

    def test_bad_frames_raise(self):
        for raw in ("", "x", "a{not json", "a{}"):
            with pytest.raises(ProtocolError):
                parse_frame(raw)

    def test_encode_request_shapes(self):
        assert encode_request("authorize", 1, body="TOKEN") == "authorize\n1\n\nTOKEN"
        assert encode_request("md/subscribeQuote", 2, body={"symbol": "MESU6"}) == \
            'md/subscribeQuote\n2\n\n{"symbol": "MESU6"}'
        assert encode_request("user/syncrequest", 3) == "user/syncrequest\n3\n\n"


class TestAuthParsing:
    def test_token_response(self):
        token = parse_token_response({
            "accessToken": "abc", "mdAccessToken": "md-abc",
            "expirationTime": "2026-08-16T20:00:00Z"})
        assert token.access_token == "abc"
        assert token.expiration == datetime(2026, 8, 16, 20, 0,
                                            tzinfo=timezone.utc)
        assert token.expires_within(timedelta(days=365))

    def test_penalty_response_raises(self):
        with pytest.raises(PenaltyResponse) as exc:
            parse_token_response({"p-ticket": "t1", "p-time": 30,
                                  "p-captcha": True})
        assert exc.value.captcha
        assert exc.value.penalty_seconds == 30

    def test_garbage_raises_auth_error(self):
        with pytest.raises(AuthError):
            parse_token_response({"errorText": "wrong password"})

    def test_parse_penalty_none_on_clean(self):
        assert parse_penalty({"accessToken": "x"}) is None

    def test_credentials_from_env_requires_all(self, monkeypatch):
        for var in ("TRADOVATE_USERNAME", "TRADOVATE_PASSWORD",
                    "TRADOVATE_APP_ID", "TRADOVATE_CID",
                    "TRADOVATE_SECRET", "TRADOVATE_DEVICE_ID"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(AuthError, match="TRADOVATE_USERNAME"):
            Credentials.from_env()


class TestEndpointSelection:
    def _config(self, dry_run, live):
        from src.config_loader import load_config
        import yaml
        cfg = load_config(Path(__file__).resolve().parents[1] / "config")
        cfg.raw["mode"] = {"dry_run": dry_run, "live_trading": live}
        from src.config_loader import _execution_mode
        cfg.mode = _execution_mode(cfg.raw["mode"], [])
        return cfg

    def test_demo_unless_both_switches(self):
        from src.auth.tradovate_auth import rest_base_url
        assert "demo" in rest_base_url(self._config(True, False))
        assert "demo" in rest_base_url(self._config(False, False))
        assert "live" in rest_base_url(self._config(False, True))


class TestTokenBucket:
    def test_burst_then_throttle(self):
        async def scenario():
            bucket = TokenBucket(rate=50.0, capacity=2)
            start = time.monotonic()
            for _ in range(4):          # 2 burst + 2 refilled @ 50/s
                await bucket.acquire()
            return time.monotonic() - start
        elapsed = asyncio.run(scenario())
        assert elapsed >= 0.03          # had to wait for refill
        assert elapsed < 1.0


class TestPenaltyStore:
    def test_record_pending_clear(self, tmp_path):
        store = PenaltyStore(tmp_path / "pt.json")
        assert store.pending("order/placeorder") is None
        store.record("order/placeorder", "t-123", 60)
        pending = store.pending("order/placeorder")
        assert pending["ticket"] == "t-123"
        store.clear("order/placeorder")
        assert store.pending("order/placeorder") is None

    def test_expired_tickets_dropped_on_load(self, tmp_path):
        path = tmp_path / "pt.json"
        path.write_text(json.dumps(
            {"ep": {"ticket": "old", "retry_at": time.time() - 10}}))
        assert PenaltyStore(path).load() == {}


class _FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Yields queued responses; records request bodies."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, json=None, headers=None):
        self.calls.append({"method": method, "url": url, "json": json})
        return self.responses.pop(0)

    def post(self, url, json=None):
        return self.request("POST", url, json)


def _gateway(tmp_path, responses):
    from src.client.gateway import Gateway
    from src.config_loader import load_config
    config = load_config(Path(__file__).resolve().parents[1] / "config")
    config.raw["database"] = {"path": str(tmp_path / "bot.db")}
    creds = Credentials("u", "p", "app", 1, "sec", "dev")
    gw = Gateway(config, _FakeSession(responses), credentials=creds,
                 penalty_path=tmp_path / "pt.json")
    gw.auth.token = parse_token_response({
        "accessToken": "tok", "expirationTime": "2027-01-01T00:00:00Z"})
    return gw


class TestGateway:
    def test_clean_request(self, tmp_path):
        gw = _gateway(tmp_path, [_FakeResponse(200, [{"id": 1}])])
        result = asyncio.run(gw.request("GET", "account/list"))
        assert result == [{"id": 1}]

    def test_429_backoff_then_success(self, tmp_path, monkeypatch):
        async def no_sleep(_):
            pass
        monkeypatch.setattr("src.client.gateway.asyncio.sleep", no_sleep)
        gw = _gateway(tmp_path, [
            _FakeResponse(429, {}),
            _FakeResponse(200, {"ok": True}),
        ])
        assert asyncio.run(gw.request("POST", "order/placeorder", {})) == {"ok": True}

    def test_penalty_persisted_and_replayed(self, tmp_path, monkeypatch):
        async def no_sleep(_):
            pass
        monkeypatch.setattr("src.client.gateway.asyncio.sleep", no_sleep)
        gw = _gateway(tmp_path, [
            _FakeResponse(200, {"p-ticket": "t-9", "p-time": 1}),
            _FakeResponse(200, {"ok": True}),
        ])
        result = asyncio.run(gw.request("POST", "order/placeorder", {"x": 1}))
        assert result == {"ok": True}
        # replay carried the ticket, and success cleared the store
        second_call = gw.session.calls[-1]
        assert second_call["json"]["p-ticket"] == "t-9"
        assert gw.penalties.pending("order/placeorder") is None

    def test_captcha_penalty_raises(self, tmp_path):
        from src.client.gateway import GatewayError
        gw = _gateway(tmp_path, [
            _FakeResponse(200, {"p-ticket": "t", "p-time": 3600,
                                "p-captcha": True})])
        with pytest.raises(GatewayError, match="captcha"):
            asyncio.run(gw.request("POST", "order/placeorder", {}))
        # but the ticket IS persisted for the restart case
        assert gw.penalties.pending("order/placeorder") is not None


class TestRestBodies:
    def _rest(self, tmp_path, responses):
        return TradovateREST(_gateway(tmp_path, responses))

    def test_is_automated_always_stamped(self, tmp_path):
        rest = self._rest(tmp_path, [_FakeResponse(200, {})])
        asyncio.run(rest.place_order(
            account_spec="spec", account_id=1, action="Buy",
            symbol="MESU6", qty=1, order_type="Limit", price=6400.25))
        body = rest.gw.session.calls[0]["json"]
        assert body["isAutomated"] is True
        assert body["symbol"] == "MESU6"

    def test_oso_bracket_opposes_entry(self, tmp_path):
        rest = self._rest(tmp_path, [_FakeResponse(200, {})])
        asyncio.run(rest.place_oso(
            account_spec="spec", account_id=1, action="Buy",
            symbol="YMU6", qty=1, order_type="Stop", stop_price=40000,
            bracket_stop_price=39900))
        body = rest.gw.session.calls[0]["json"]
        assert body["bracket1"] == {"action": "Sell", "orderType": "Stop",
                                    "stopPrice": 39900}

    def test_invalid_action_rejected(self, tmp_path):
        rest = self._rest(tmp_path, [])
        with pytest.raises(ValueError, match="Buy\\|Sell"):
            asyncio.run(rest.place_order(
                account_spec="s", account_id=1, action="buy",
                symbol="MESU6", qty=1, order_type="Limit"))
