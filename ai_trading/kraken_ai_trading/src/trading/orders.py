import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..client.websocket import KrakenWebSocket


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"
    STOP_LOSS = "stop-loss"
    STOP_LOSS_LIMIT = "stop-loss-limit"
    TAKE_PROFIT = "take-profit"
    TAKE_PROFIT_LIMIT = "take-profit-limit"
    TRAILING_STOP = "trailing-stop"
    TRAILING_STOP_LIMIT = "trailing-stop-limit"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TimeInForce(str, Enum):
    GTC = "gtc"   # Good Till Cancelled
    GTD = "gtd"   # Good Till Date
    IOC = "ioc"   # Immediate Or Cancel


class OrderStatus(str, Enum):
    PENDING_NEW = "pending_new"
    NEW = "new"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    AMENDED = "amended"


@dataclass
class Order:
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: float
    price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    cl_ord_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING_NEW
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    fees: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.status in (OrderStatus.PENDING_NEW, OrderStatus.NEW, OrderStatus.PARTIAL)

    @property
    def is_done(self) -> bool:
        return self.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.EXPIRED)


class OrderManager:
    """
    Places and manages orders via the Kraken WebSocket v2 authenticated channel.
    Tracks local order state and reconciles it with incoming execution events.
    """

    def __init__(self, ws: "KrakenWebSocket", token: str) -> None:
        self._ws = ws
        self._token = token
        # order_id → Order (confirmed by exchange)
        self._orders: dict[str, Order] = {}
        # cl_ord_id → Order (pending exchange acknowledgement)
        self._pending: dict[str, Order] = {}
        self._req_id = 0
        self.log = get_logger(__name__)

    def _next_req_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def refresh_token(self, token: str) -> None:
        self._token = token

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    async def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        qty: float,
        price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
        post_only: bool = False,
        reduce_only: bool = False,
    ) -> Optional[Order]:
        """Returns the Order on success, None if the socket was down and the order was not sent."""
        order = Order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            qty=qty,
            price=price,
            time_in_force=time_in_force,
        )
        self._pending[order.cl_ord_id] = order
        sent = await self._ws.send({
            "method": "add_order",
            "params": {
                "order_type": OrderType.LIMIT,
                "side": side,
                "order_qty": qty,
                "symbol": symbol,
                "limit_price": price,
                "time_in_force": time_in_force,
                "post_only": post_only,
                "reduce_only": reduce_only,
                "cl_ord_id": order.cl_ord_id,
                "token": self._token,
            },
            "req_id": self._next_req_id(),
        })
        if not sent:
            self._pending.pop(order.cl_ord_id, None)
            self.log.warning("LIMIT order not sent (socket down) — dropped %s", order.cl_ord_id)
            return None
        self.log.info("LIMIT %s %s %.6f @ %.4f cl=%s", side, symbol, qty, price, order.cl_ord_id)
        return order

    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        qty: float,
    ) -> Optional[Order]:
        """Returns the Order on success, None if the socket was down and the order was not sent."""
        order = Order(symbol=symbol, side=side, order_type=OrderType.MARKET, qty=qty)
        self._pending[order.cl_ord_id] = order
        sent = await self._ws.send({
            "method": "add_order",
            "params": {
                "order_type": OrderType.MARKET,
                "side": side,
                "order_qty": qty,
                "symbol": symbol,
                "cl_ord_id": order.cl_ord_id,
                "token": self._token,
            },
            "req_id": self._next_req_id(),
        })
        if not sent:
            self._pending.pop(order.cl_ord_id, None)
            self.log.warning("MARKET order not sent (socket down) — dropped %s", order.cl_ord_id)
            return None
        self.log.info("MARKET %s %s %.6f cl=%s", side, symbol, qty, order.cl_ord_id)
        return order

    async def place_batch(self, orders: list[dict]) -> None:
        """Send up to 15 orders in a single message (Kraken batch endpoint)."""
        await self._ws.send({
            "method": "batch_add",
            "params": {"orders": orders, "symbol": orders[0]["symbol"], "token": self._token},
            "req_id": self._next_req_id(),
        })

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    async def cancel_order(self, order_id: str) -> None:
        await self._ws.send({
            "method": "cancel_order",
            "params": {"order_id": [order_id], "token": self._token},
            "req_id": self._next_req_id(),
        })
        self.log.info("Cancel requested for %s", order_id)

    async def cancel_all(self) -> None:
        await self._ws.send({
            "method": "cancel_all",
            "params": {"token": self._token},
            "req_id": self._next_req_id(),
        })
        self.log.info("Cancel-all requested")

    async def amend_order(
        self,
        order_id: str,
        new_price: Optional[float] = None,
        new_qty: Optional[float] = None,
    ) -> None:
        params: dict = {"order_id": order_id, "token": self._token}
        if new_price is not None:
            params["limit_price"] = new_price
        if new_qty is not None:
            params["order_qty"] = new_qty
        await self._ws.send({
            "method": "amend_order",
            "params": params,
            "req_id": self._next_req_id(),
        })
        self.log.info("Amend %s price=%s qty=%s", order_id, new_price, new_qty)

    # ------------------------------------------------------------------
    # Execution reconciliation  (called by the message router)
    # ------------------------------------------------------------------

    def on_execution(self, msg: dict) -> None:
        """Process an execution event from the 'executions' WebSocket channel."""
        for event in msg.get("data", []):
            order_id = event.get("order_id")
            cl_ord_id = event.get("cl_ord_id")
            exec_type = event.get("exec_type", "")

            # promote pending → confirmed
            order: Optional[Order] = None
            if cl_ord_id and cl_ord_id in self._pending:
                order = self._pending.pop(cl_ord_id)
                if order_id:
                    order.order_id = order_id
                    self._orders[order_id] = order
            elif order_id and order_id in self._orders:
                order = self._orders[order_id]

            if not order:
                return

            # update status
            try:
                order.status = OrderStatus(exec_type)
            except ValueError:
                pass

            # update fill state on trade events
            if exec_type == "trade":
                order.filled_qty = float(event.get("cum_qty", order.filled_qty))
                order.avg_fill_price = float(event.get("avg_price", order.avg_fill_price))
                order.fees += float(event.get("cost", 0))
                self.log.info(
                    "FILL %s %s filled=%.6f avg=%.4f fees=%.4f",
                    order.side, order.symbol, order.filled_qty, order.avg_fill_price, order.fees,
                )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_open_orders(self) -> list[Order]:
        return [o for o in self._orders.values() if o.is_open]

    def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    def get_all_orders(self) -> list[Order]:
        return list(self._orders.values())
