"""Session state machine (§6).

Day session: opens 08:00 ET, closes 16:00 ET the same day. At
(close − flatten_buffer_minutes) every position is flattened and every
working order cancelled; outside the window no orders are placed. The
session exists only on days listed in trade_days.

All public methods take timezone-aware datetimes (any zone — converted to
the configured session timezone internally). Naive datetimes are rejected:
a naive "now" silently interpreted in the wrong zone is exactly how bots
trade into the maintenance window.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")  # weekday() order


def _parse_hhmm(value: str) -> time:
    hour, minute = value.strip().split(":")
    return time(int(hour), int(minute))


class SessionState(Enum):
    CLOSED = "closed"        # outside the window — no orders of any kind
    OPEN = "open"            # entries and exits allowed
    FLATTENING = "flattening"  # close buffer — no new entries, flatten + cancel


class SessionManager:
    def __init__(self, session_cfg: dict):
        self.tz = ZoneInfo(session_cfg["timezone"])
        self.open_t = _parse_hhmm(session_cfg["open"])
        self.close_t = _parse_hhmm(session_cfg["close"])
        self.flatten_buffer = timedelta(
            minutes=int(session_cfg["flatten_buffer_minutes"]))
        self.trade_days = frozenset(session_cfg["trade_days"])
        unknown = self.trade_days - set(DAY_NAMES)
        if unknown:
            raise ValueError(f"session.trade_days: unknown days {sorted(unknown)}")

    def _local(self, now: datetime) -> datetime:
        if now.tzinfo is None:
            raise ValueError("SessionManager requires timezone-aware datetimes")
        return now.astimezone(self.tz)

    def state(self, now: datetime) -> SessionState:
        local = self._local(now)
        if DAY_NAMES[local.weekday()] not in self.trade_days:
            return SessionState.CLOSED
        open_dt = local.replace(hour=self.open_t.hour, minute=self.open_t.minute,
                                second=0, microsecond=0)
        close_dt = local.replace(hour=self.close_t.hour, minute=self.close_t.minute,
                                 second=0, microsecond=0)
        if not (open_dt <= local < close_dt):
            return SessionState.CLOSED
        if local >= close_dt - self.flatten_buffer:
            return SessionState.FLATTENING
        return SessionState.OPEN

    def is_entry_allowed(self, now: datetime) -> bool:
        return self.state(now) is SessionState.OPEN

    def should_flatten(self, now: datetime) -> bool:
        """True from (close − buffer) onward — including after close and on
        non-trade days, so a position that somehow survived (crash restart,
        clock skew) is flattened at the first opportunity."""
        return self.state(now) is not SessionState.OPEN
