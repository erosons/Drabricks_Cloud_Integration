import asyncio
import urllib.parse
from typing import Any, Optional

import aiohttp

from ..auth.signer import KrakenAuth
from ..utils.logger import get_logger


class KrakenAPIError(Exception):
    pass


class KrakenRESTClient:
    BASE_URL = "https://api.kraken.com"

    def __init__(self, auth: KrakenAuth) -> None:
        self.auth = auth
        self._session: Optional[aiohttp.ClientSession] = None
        self.log = get_logger(__name__)

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "KrakenRESTClient":
        await self.start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _public(self, endpoint: str, params: Optional[dict] = None) -> Any:
        url = f"{self.BASE_URL}/0/public/{endpoint}"
        async with self._session.get(url, params=params) as resp:
            resp.raise_for_status()
            body = await resp.json()
        if body.get("error"):
            raise KrakenAPIError(body["error"])
        return body["result"]

    async def _private(self, endpoint: str, data: Optional[dict] = None) -> Any:
        urlpath = f"/0/private/{endpoint}"
        url = f"{self.BASE_URL}{urlpath}"
        for attempt in range(2):
            payload: dict = dict(data or {})
            payload["nonce"] = self.auth.generate_nonce()
            headers = self.auth.get_headers(urlpath, payload)
            body_str = urllib.parse.urlencode(payload)
            async with self._session.post(url, headers=headers, data=body_str) as resp:
                resp.raise_for_status()
                body = await resp.json()
            errors = body.get("error", [])
            if errors and "EAPI:Invalid nonce" in errors and attempt == 0:
                self.log.debug("Nonce rejected by Kraken — retrying with fresh nonce")
                continue
            if errors:
                raise KrakenAPIError(errors)
            return body["result"]
        raise KrakenAPIError(["EAPI:Invalid nonce"])

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def get_balance(self) -> dict:
        return await self._private("Balance")

    async def get_trade_balance(self, asset: str = "ZUSD") -> dict:
        return await self._private("TradeBalance", {"asset": asset})

    # ------------------------------------------------------------------
    # WebSocket token  (required before any authenticated WS connection)
    # ------------------------------------------------------------------

    async def get_websockets_token(self) -> str:
        # Retry with exponential backoff on rate-limit errors.
        # 84 pairs restart simultaneously after a deploy and all hit this endpoint at once.
        for attempt in range(8):
            try:
                result = await self._private("GetWebSocketsToken")
                return result["token"]
            except KrakenAPIError as exc:
                if "Rate limit" in str(exc) and attempt < 7:
                    wait = min(5 * 2 ** attempt, 120)
                    self.log.warning("GetWebSocketsToken rate-limited — retry %d/7 in %ds", attempt + 1, wait)
                    await asyncio.sleep(wait)
                else:
                    raise

    # ------------------------------------------------------------------
    # Orders (REST fallback — primary order placement is via WebSocket)
    # ------------------------------------------------------------------

    async def get_open_orders(self, trades: bool = False) -> dict:
        return await self._private("OpenOrders", {"trades": trades})

    async def get_closed_orders(self, **kwargs: Any) -> dict:
        return await self._private("ClosedOrders", kwargs if kwargs else None)

    async def add_order(
        self,
        ordertype: str,
        side: str,
        volume: str,
        pair: str,
        **kwargs: Any,
    ) -> dict:
        data = {"ordertype": ordertype, "type": side, "volume": volume, "pair": pair, **kwargs}
        return await self._private("AddOrder", data)

    async def cancel_order(self, txid: str) -> dict:
        return await self._private("CancelOrder", {"txid": txid})

    async def cancel_all_orders(self) -> dict:
        return await self._private("CancelAll")

    async def cancel_all_orders_after(self, timeout: int) -> dict:
        """Dead-man's switch: cancel all open orders if not refreshed within `timeout` seconds."""
        return await self._private("CancelAllOrdersAfter", {"timeout": timeout})

    # ------------------------------------------------------------------
    # Market data (REST)
    # ------------------------------------------------------------------

    async def get_ticker(self, pair: str) -> dict:
        return await self._public("Ticker", {"pair": pair})

    async def get_order_book(self, pair: str, count: int = 10) -> dict:
        return await self._public("Depth", {"pair": pair, "count": count})

    async def get_tradable_pairs(self, pair: Optional[str] = None) -> dict:
        params = {"pair": pair} if pair else None
        return await self._public("AssetPairs", params)
