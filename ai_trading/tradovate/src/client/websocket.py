"""Tradovate WebSocket layer (docs/API-document.md).

Split in two:
  * pure frame codec (encode_request / parse_frame) — fully unit-tested
  * TradovateSocket — auto-reconnecting connection using the codec

Protocol (verified against tradovate/example-api-js):
  frames: 'o' open, 'h' server heartbeat, 'a'+JSON array of messages, 'c' close
  request text: "url\\nid\\nquery\\nbody"; responses echo {"i": id, "s": .., "d": ..}
  client heartbeat: the literal string "[]" every ~2.5 s
  authorize: url "authorize", body = access token (MD socket: mdAccessToken)

Coalescing rule (§17 attestation #24–25): one 'a' frame may batch messages
for several symbols and stale updates may be dropped — consumers must treat
gaps as drop-and-resync, never assume continuity.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

import websockets

log = logging.getLogger("tradovate_ws")

HEARTBEAT_INTERVAL = 2.5   # seconds
HEARTBEAT_FRAME = "[]"


class ProtocolError(Exception):
    pass


@dataclass(frozen=True)
class Frame:
    kind: str                    # 'o' | 'h' | 'a' | 'c'
    messages: tuple = ()         # parsed JSON messages for 'a' frames


def parse_frame(raw: str) -> Frame:
    if not raw:
        raise ProtocolError("empty frame")
    kind, payload = raw[0], raw[1:]
    if kind in ("o", "h", "c"):
        return Frame(kind)
    if kind == "a":
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"bad 'a' frame payload: {payload[:100]!r}") from exc
        if not isinstance(data, list):
            raise ProtocolError("'a' frame payload was not a list")
        return Frame("a", tuple(data))
    raise ProtocolError(f"unknown frame indicator {kind!r}")


def encode_request(url: str, request_id: int, query: str = "",
                   body: dict | str | None = None) -> str:
    if body is None:
        body_s = ""
    elif isinstance(body, str):
        body_s = body                    # authorize sends the raw token
    else:
        body_s = json.dumps(body)
    return f"{url}\n{request_id}\n{query}\n{body_s}"


@dataclass
class _Pending:
    future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())


class TradovateSocket:
    """One socket (trading or MD). request() correlates responses by id;
    subscription events (no 'i') go to the event callback."""

    def __init__(self, url: str, access_token: str, on_event=None,
                 name: str = "ws"):
        self.url = url
        self.access_token = access_token
        self.on_event = on_event or (lambda msg: None)
        self.name = name
        self._ws = None
        self._counter = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._tasks: list[asyncio.Task] = []
        self.connected = asyncio.Event()

    async def connect(self) -> None:
        self._ws = await websockets.connect(self.url)
        opening = parse_frame(await self._ws.recv())
        if opening.kind != "o":
            raise ProtocolError(f"expected open frame, got {opening.kind!r}")
        self._tasks = [
            asyncio.create_task(self._reader(), name=f"{self.name}-reader"),
            asyncio.create_task(self._heartbeats(), name=f"{self.name}-hb"),
        ]
        status = await self.request("authorize", body=self.access_token)
        if status.get("s") != 200:
            raise ProtocolError(f"authorize failed: {status}")
        self.connected.set()
        log.info("[%s] connected + authorized", self.name)

    async def close(self) -> None:
        self.connected.clear()
        for task in self._tasks:
            task.cancel()
        if self._ws is not None:
            await self._ws.close()

    async def request(self, url: str, query: str = "",
                      body: dict | str | None = None, timeout: float = 10.0) -> dict:
        self._counter += 1
        request_id = self._counter
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._ws.send(encode_request(url, request_id, query, body))
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(request_id, None)

    async def _reader(self) -> None:
        try:
            async for raw in self._ws:
                frame = parse_frame(raw)
                if frame.kind != "a":
                    continue
                for msg in frame.messages:
                    request_id = msg.get("i") if isinstance(msg, dict) else None
                    future = self._pending.get(request_id)
                    if future is not None and not future.done():
                        future.set_result(msg)
                    else:
                        self.on_event(msg)
        except websockets.ConnectionClosed as exc:
            log.warning("[%s] connection closed: %s", self.name, exc)
            self.connected.clear()

    async def _heartbeats(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await self._ws.send(HEARTBEAT_FRAME)
            except websockets.ConnectionClosed:
                return
