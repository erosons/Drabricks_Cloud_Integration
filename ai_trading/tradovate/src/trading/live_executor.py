"""Live/demo order routing — the Executor protocol against Tradovate REST.

Active only when dry_run: false. Every entry goes out as an OSO bracket
(placeoso, verified on demo) so the protective stop exists server-side from
the moment of fill. The returned orderId/oso1Id are tracked so the quadrant
trail can modify the bracket stop and blackout/session logic can cancel the
working entry.

Fill confirmations do NOT come from here — they arrive on the trading
socket's user/syncrequest stream and reach engine.on_fill via
UserSyncRouter (user_sync.py).

Failure semantics: enter() returns False on any rejection so the engine
simply doesn't count an entry. modify/flatten/cancel failures are logged
(flatten at CRITICAL — the server-side bracket stop still protects the
position) but never raised into the engine loop.
"""

from __future__ import annotations

from src.client.rest import TradovateREST
from src.utils.logger import get_logger


def _failure(resp) -> str | None:
    """Tradovate order endpoints report rejection inline, HTTP 200."""
    if not isinstance(resp, dict):
        return f"unexpected response: {resp!r}"
    if resp.get("failureReason") or resp.get("failureText"):
        return f"{resp.get('failureReason')}: {resp.get('failureText')}"
    return None


class LiveExecutor:
    def __init__(self, rest: TradovateREST, *, account_spec: str,
                 account_id: int, contract_id: int, product: str):
        self.rest = rest
        self.account_spec = account_spec
        self.account_id = account_id
        self.contract_id = contract_id
        self.log = get_logger(f"live.{product}")
        self.entry_order_id: int | None = None
        self.stop_order_id: int | None = None
        self._qty = 0
        self._net = 0

    def note_fill(self, side: str, qty: int) -> None:
        """Fed every routed fill (main.py wires it ahead of engine.on_fill).
        When the net position round-trips to flat — e.g. the server-side
        bracket filled without an engine flatten — release the one-bracket
        entry guard. If fill events stop arriving, _net stays nonzero and
        the guard holds: fail-safe against trading blind."""
        self._net += qty if side == "buy" else -qty
        if self._net == 0:
            self.entry_order_id = None
            self.stop_order_id = None
            self._qty = 0

    async def enter(self, symbol: str, side: str, qty: int,
                    limit_price: float, bracket_stop: float) -> bool:
        # one-bracket cap: if fill events are never recognized (unverified
        # user-sync shapes) the engine's position stays 0 and it would re-enter
        # after every cooldown — refuse until flatten/cancel clears the entry
        if self.entry_order_id is not None:
            self.log.error("ENTER %s refused: orderId=%s still tracked and "
                           "unresolved — fill events may not be arriving",
                           symbol, self.entry_order_id)
            return False
        action = "Buy" if side == "buy" else "Sell"
        try:
            resp = await self.rest.place_oso(
                account_spec=self.account_spec, account_id=self.account_id,
                action=action, symbol=symbol, qty=qty, order_type="Limit",
                price=limit_price, bracket_stop_price=bracket_stop)
        except Exception as exc:
            self.log.error("ENTER %s %s x%d: request failed: %s",
                           action, symbol, qty, exc)
            return False
        reason = _failure(resp)
        if reason is not None or "orderId" not in resp:
            self.log.error("ENTER %s %s x%d REJECTED: %s",
                           action, symbol, qty, reason or resp)
            return False
        self.entry_order_id = resp["orderId"]
        self.stop_order_id = resp.get("oso1Id")
        self._qty = qty
        self.log.info("ENTER %s %s x%d limit=%.2f bracket_stop=%.2f "
                      "→ orderId=%s oso1Id=%s", action, symbol, qty,
                      limit_price, bracket_stop,
                      self.entry_order_id, self.stop_order_id)
        return True

    async def modify_stop(self, symbol: str, new_stop: float) -> None:
        if self.stop_order_id is None:
            self.log.warning("MODIFY STOP %s → %.2f: no tracked bracket stop",
                             symbol, new_stop)
            return
        try:
            resp = await self.rest.modify_order(
                self.stop_order_id, order_qty=self._qty,
                order_type="Stop", stop_price=new_stop)
        except Exception as exc:
            self.log.error("MODIFY STOP %s → %.2f failed: %s",
                           symbol, new_stop, exc)
            return
        reason = _failure(resp)
        if reason is not None:
            self.log.error("MODIFY STOP %s → %.2f REJECTED: %s",
                           symbol, new_stop, reason)
        else:
            self.log.info("MODIFY STOP %s → %.2f (orderId=%s)",
                          symbol, new_stop, self.stop_order_id)

    async def flatten(self, symbol: str, reason: str) -> None:
        # cancel the bracket stop first so liquidation cannot race it into
        # an unintended reversal fill
        if self.stop_order_id is not None:
            await self._cancel(self.stop_order_id, f"flatten: {reason}")
            self.stop_order_id = None
        try:
            resp = await self.rest.liquidate_position(
                self.account_id, self.contract_id)
        except Exception as exc:
            self.log.critical("FLATTEN %s (%s) FAILED — position may still be "
                              "open: %s", symbol, reason, exc)
            return
        fail = _failure(resp)
        if fail is not None:
            self.log.critical("FLATTEN %s (%s) REJECTED — position may still "
                              "be open: %s", symbol, reason, fail)
        else:
            self.log.info("FLATTEN %s (%s)", symbol, reason)
        self.entry_order_id = None
        self._qty = 0

    async def cancel_working(self, symbol: str, reason: str) -> None:
        """Cancel the working ENTRY only. An unfilled OSO entry takes its
        bracket with it; a filled entry's protective stop must survive a
        blackout-start cancel, so the stop is only removed via flatten()."""
        if self.entry_order_id is None:
            return
        await self._cancel(self.entry_order_id, reason)
        self.entry_order_id = None

    async def _cancel(self, order_id: int, reason: str) -> None:
        try:
            resp = await self.rest.cancel_order(order_id)
        except Exception as exc:
            self.log.error("CANCEL orderId=%s (%s) failed: %s",
                           order_id, reason, exc)
            return
        fail = _failure(resp)
        if fail is not None:
            # routinely means "already filled/cancelled" — not actionable
            self.log.info("CANCEL orderId=%s (%s): not cancellable (%s)",
                          order_id, reason, fail)
        else:
            self.log.info("CANCEL orderId=%s (%s)", order_id, reason)
