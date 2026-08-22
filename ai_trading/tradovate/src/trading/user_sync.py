"""User-data event router — trading-socket user/syncrequest events → engine.

Pure routing (fully testable offline), mirror of market_data/stream.MdRouter;
the socket itself is owned by main.py.

Event shapes VERIFIED on demo 2026-08-18 (scripts/capture_user_sync.py,
logs/user_sync_capture_20260818T*.jsonl; real frames are fixtures in
tests/test_live_executor.py):

  {"e": "props", "d": {"entityType": "fill",  "eventType": "Created",
                       "entity": {"contractId": .., "action": "Buy"/"Sell",
                                  "qty": .., "price": .., ...}}}
  {"e": "props", "d": {"entityType": "order", "eventType": "Updated",
                       "entity": {"ordStatus": "PendingNew"/"Working"/
                                  "Filled"/"Canceled"/"Suspended"/
                                  "Rejected", ...}}}

Rejections verified live (MaxOrderQtyLimitReached): the order frame carries
ordStatus == "Rejected" with the order id — exactly what the nack branch
keys on — while the reason text arrives separately on a commandReport
entity (commandStatus == "RiskRejected", rejectReason, text). Partial
fills arrive as multiple independent fill Created frames (one per partial
qty), each routed on its own.

Anything unrecognized is logged and dropped — never guessed at (§17).
"""

from __future__ import annotations

from typing import Awaitable, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)


class UserSyncRouter:
    def __init__(self, contract_id: int,
                 on_fill: Callable[..., Awaitable[None]],
                 on_order_nack: Callable[..., Awaitable[None]]):
        self.contract_id = contract_id
        self.on_fill = on_fill
        self.on_order_nack = on_order_nack

    async def route(self, msg: dict) -> None:
        if not isinstance(msg, dict) or msg.get("e") != "props":
            return
        data = msg.get("d") or {}
        entity_type = data.get("entityType")
        entity = data.get("entity") or {}

        if entity_type == "fill" and data.get("eventType") == "Created":
            if entity.get("contractId") != self.contract_id:
                return
            try:
                side = str(entity["action"]).lower()
                qty = int(entity["qty"])
                price = float(entity["price"])
            except (KeyError, TypeError, ValueError):
                log.error("unparseable fill event — verify shapes at soak: %r",
                          entity)
                return
            log.info("FILL %s x%d @ %.2f", side, qty, price)
            await self.on_fill(side, qty, price)

        elif entity_type == "order" and entity.get("ordStatus") == "Rejected":
            log.warning("order REJECTED: %r", entity)
            await self.on_order_nack(str(entity.get("id", "")))
