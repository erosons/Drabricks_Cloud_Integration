"""Typed Tradovate REST calls, all through the gateway (docs/API-document.md).

isAutomated is stamped True on EVERY order here — hard-coded, not
configurable (§17 attestation #7).
"""

from __future__ import annotations

from src.client.gateway import Gateway

ORDER_TYPES = frozenset({
    "Market", "Limit", "Stop", "StopLimit", "MIT",
    "TrailingStop", "TrailingStopLimit",
})


class TradovateREST:
    def __init__(self, gateway: Gateway):
        self.gw = gateway

    async def account_list(self) -> list:
        return await self.gw.request("GET", "account/list")

    async def cash_balance_snapshot(self, account_id: int) -> dict:
        return await self.gw.request(
            "POST", "cashBalance/getcashbalancesnapshot",
            {"accountId": account_id})

    def _order_body(self, *, account_spec: str, account_id: int, action: str,
                    symbol: str, qty: int, order_type: str,
                    price: float | None = None,
                    stop_price: float | None = None) -> dict:
        if action not in ("Buy", "Sell"):
            raise ValueError(f"action must be Buy|Sell, got {action!r}")
        if order_type not in ORDER_TYPES:
            raise ValueError(f"unknown orderType {order_type!r}")
        body = {
            "accountSpec": account_spec,
            "accountId": account_id,
            "action": action,
            "symbol": symbol,          # ACTIVE month code, never the root (§4)
            "orderQty": qty,
            "orderType": order_type,
            "timeInForce": "Day",
            "isAutomated": True,       # attestation #7 — never configurable
        }
        if price is not None:
            body["price"] = price
        if stop_price is not None:
            body["stopPrice"] = stop_price
        return body

    async def place_order(self, **kwargs) -> dict:
        return await self.gw.request(
            "POST", "order/placeorder", self._order_body(**kwargs))

    async def place_oso(self, *, bracket_stop_price: float, **kwargs) -> dict:
        """Entry + server-side protective stop from the moment of fill (§7).
        The bracket's action is the opposite side of the entry."""
        body = self._order_body(**kwargs)
        body["bracket1"] = {
            "action": "Sell" if body["action"] == "Buy" else "Buy",
            "orderType": "Stop",
            "stopPrice": bracket_stop_price,
        }
        return await self.gw.request("POST", "order/placeoso", body)

    async def modify_order(self, order_id: int, *, order_qty: int,
                           order_type: str, price: float | None = None,
                           stop_price: float | None = None) -> dict:
        body = {"orderId": order_id, "orderQty": order_qty,
                "orderType": order_type, "isAutomated": True}
        if price is not None:
            body["price"] = price
        if stop_price is not None:
            body["stopPrice"] = stop_price
        return await self.gw.request("POST", "order/modifyorder", body)

    async def cancel_order(self, order_id: int) -> dict:
        return await self.gw.request(
            "POST", "order/cancelorder", {"orderId": order_id, "isAutomated": True})

    async def liquidate_position(self, account_id: int, contract_id: int) -> dict:
        return await self.gw.request(
            "POST", "order/liquidateposition",
            {"accountId": account_id, "contractId": contract_id,
             "admin": False, "isAutomated": True})
