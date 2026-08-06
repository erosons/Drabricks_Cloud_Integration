import asyncio
import json
import time
from typing import Any, Awaitable, Callable, Optional

import websockets
import websockets.exceptions

from ..utils.logger import get_logger

MessageHandler = Callable[[dict], Awaitable[None]]


class KrakenWebSocket:
    """
    Async WebSocket v2 client for Kraken.

    Handles:
    - Auto-reconnect with exponential backoff
    - Subscription replay on reconnect
    - Server ping/pong (websockets handles natively via ping_interval)
    - Connected event so callers can subscribe after the socket is live
    """

    PUBLIC_URL = "wss://ws.kraken.com/v2"
    AUTH_URL = "wss://ws-auth.kraken.com/v2"

    def __init__(
        self,
        authenticated: bool = False,
        on_message: Optional[MessageHandler] = None,
        on_connect: Optional[Callable[[], Awaitable[None]]] = None,
        on_reconnect: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        self.url = self.AUTH_URL if authenticated else self.PUBLIC_URL
        self.on_message = on_message
        self.on_connect = on_connect
        self.on_reconnect = on_reconnect  # called before subscription replay on every reconnect

        self._ws: Optional[Any] = None  # websockets.asyncio.client.ClientConnection (v13+)
        self._running = False
        self._subscriptions: list[dict] = []
        self._req_id = 0
        self._connected = asyncio.Event()
        self.log = get_logger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the connection loop (runs until disconnect() is called)."""
        self._running = True
        await self._run_loop()

    async def disconnect(self) -> None:
        self._running = False
        self._connected.clear()
        if self._ws:
            await self._ws.close()

    async def wait_connected(self) -> None:
        """Block until the socket is live."""
        await self._connected.wait()

    async def subscribe(self, params: dict) -> None:
        """Subscribe to a channel; replays automatically on reconnect."""
        msg = {"method": "subscribe", "params": params, "req_id": self._next_req_id()}
        self._subscriptions.append(msg)
        await self.send(msg)

    async def unsubscribe(self, params: dict) -> None:
        await self.send({"method": "unsubscribe", "params": params, "req_id": self._next_req_id()})

    async def send(self, message: dict) -> bool:
        """Send a message. Returns True on success, False if the socket is down or send fails."""
        if self._ws is not None and self._connected.is_set():
            try:
                await self._ws.send(json.dumps(message))
                return True
            except Exception as exc:
                self.log.warning("Send failed: %s", exc)
                return False
        else:
            self.log.warning("Cannot send — socket not connected")
            return False

    async def ping(self) -> None:
        await self.send({"method": "ping", "req_id": self._next_req_id()})

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_req_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def _run_loop(self) -> None:
        backoff = 1.0
        first_connect = True

        while self._running:
            try:
                async with websockets.connect(
                    self.url,
                    ping_interval=20,   # websockets sends native WS pings every 20s
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    self._connected.set()
                    _connect_time = time.monotonic()
                    self.log.info("Connected to %s", self.url)

                    if first_connect:
                        first_connect = False
                        if self.on_connect:
                            await self.on_connect()
                    else:
                        # refresh token / state before replaying (e.g. Kraken tokens expire in 15 min)
                        if self.on_reconnect:
                            await self.on_reconnect()
                        # replay subscriptions on reconnect
                        for sub in self._subscriptions:
                            await ws.send(json.dumps(sub))
                        self.log.info("Replayed %d subscription(s) after reconnect", len(self._subscriptions))

                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            self.log.warning("Non-JSON message: %s", raw[:120])
                            continue
                        if self.on_message:
                            await self.on_message(msg)

            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.WebSocketException,
                OSError,
            ) as exc:
                if not self._running:
                    break
                self._connected.clear()
                # Only reset backoff if the connection was stable for >30s.
                # Short-lived connections keep growing the backoff so a flapping
                # auth endpoint doesn't hammer Kraken with hundreds of reconnects.
                if time.monotonic() - _connect_time > 30:
                    backoff = 1.0
                self.log.warning("Disconnected (%s), reconnecting in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
