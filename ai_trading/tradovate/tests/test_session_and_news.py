"""Frozen-time tests for the session state machine (§6) and news guard (§5)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from src.scheduling.news_guard import NewsGuard
from src.scheduling.session_manager import SessionManager, SessionState
from src.storage.db import Database

ET = ZoneInfo("America/New_York")

SESSION_CFG = {
    "timezone": "America/New_York",
    "open": "08:00",
    "close": "16:00",
    "flatten_buffer_minutes": 5,
    "trade_days": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri"],
}


def et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


class TestSessionManager:
    sm = SessionManager(SESSION_CFG)

    @pytest.mark.parametrize("now,expected", [
        (et(2026, 8, 12, 7, 59), SessionState.CLOSED),      # Wed pre-open
        (et(2026, 8, 12, 8, 0), SessionState.OPEN),         # open boundary
        (et(2026, 8, 12, 12, 30), SessionState.OPEN),
        (et(2026, 8, 12, 15, 54), SessionState.OPEN),       # last entry minute
        (et(2026, 8, 12, 15, 55), SessionState.FLATTENING), # buffer start
        (et(2026, 8, 12, 15, 59), SessionState.FLATTENING),
        (et(2026, 8, 12, 16, 0), SessionState.CLOSED),      # close boundary
        (et(2026, 8, 12, 20, 0), SessionState.CLOSED),
        (et(2026, 8, 15, 12, 0), SessionState.CLOSED),      # Saturday
        (et(2026, 8, 16, 12, 0), SessionState.OPEN),        # Sunday trades
    ])
    def test_states(self, now, expected):
        assert self.sm.state(now) is expected

    def test_utc_input_converted(self):
        # 19:56 UTC == 15:56 ET in August (EDT) → flattening
        now = datetime(2026, 8, 12, 19, 56, tzinfo=timezone.utc)
        assert self.sm.state(now) is SessionState.FLATTENING

    def test_naive_datetime_rejected(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            self.sm.state(datetime(2026, 8, 12, 12, 0))

    def test_flatten_outside_session_too(self):
        assert self.sm.should_flatten(et(2026, 8, 15, 12, 0))   # Saturday
        assert self.sm.should_flatten(et(2026, 8, 12, 16, 30))  # after close
        assert not self.sm.should_flatten(et(2026, 8, 12, 12, 0))

    def test_unknown_trade_day_rejected(self):
        with pytest.raises(ValueError, match="unknown days"):
            SessionManager(dict(SESSION_CFG, trade_days=["Funday"]))


NEWS_CFG = {
    "enabled": True,
    "blackout_before_minutes": 15,
    "blackout_after_minutes": 15,
    "position_policy": "hold",
}


@pytest.fixture
def guard(tmp_path):
    with Database(tmp_path / "bot.db") as db:
        # FOMC at 14:00 ET on 2026-08-12 == 18:00 UTC
        db.replace_news_events([
            ("2026-08-12T18:00:00+00:00", "FOMC Statement", "USD", "high"),
        ])
        yield NewsGuard(db, NEWS_CFG)


class TestNewsGuard:
    def test_blackout_window_boundaries(self, guard):
        utc = timezone.utc
        assert guard.is_entry_allowed(datetime(2026, 8, 12, 17, 44, tzinfo=utc))
        assert not guard.is_entry_allowed(datetime(2026, 8, 12, 17, 45, tzinfo=utc))
        assert not guard.is_entry_allowed(datetime(2026, 8, 12, 18, 0, tzinfo=utc))
        assert not guard.is_entry_allowed(datetime(2026, 8, 12, 18, 15, tzinfo=utc))
        assert guard.is_entry_allowed(datetime(2026, 8, 12, 18, 16, tzinfo=utc))

    def test_active_blackout_names_event(self, guard):
        blackout = guard.active_blackout(
            datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc))
        assert blackout.title == "FOMC Statement"

    def test_entering_blackout_fires_once(self, guard):
        before = datetime(2026, 8, 12, 17, 44, tzinfo=timezone.utc)
        inside1 = datetime(2026, 8, 12, 17, 45, tzinfo=timezone.utc)
        inside2 = datetime(2026, 8, 12, 17, 50, tzinfo=timezone.utc)
        assert guard.entering_blackout(before, inside1) is not None
        assert guard.entering_blackout(inside1, inside2) is None

    def test_disabled_guard_never_blocks(self, tmp_path):
        with Database(tmp_path / "bot.db") as db:
            db.replace_news_events([
                ("2026-08-12T18:00:00+00:00", "FOMC Statement", "USD", "high")])
            guard = NewsGuard(db, dict(NEWS_CFG, enabled=False))
            assert guard.is_entry_allowed(
                datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc))

    def test_reload_picks_up_daily_refresh(self, tmp_path):
        with Database(tmp_path / "bot.db") as db:
            guard = NewsGuard(db, NEWS_CFG, reload_every=timedelta(0))
            now = datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc)
            assert guard.is_entry_allowed(now)          # nothing stored yet
            db.replace_news_events([
                ("2026-08-12T18:00:00+00:00", "FOMC Statement", "USD", "high")])
            assert not guard.is_entry_allowed(now)      # reload saw the event

    def test_bad_position_policy_rejected(self, tmp_path):
        with Database(tmp_path / "bot.db") as db:
            with pytest.raises(ValueError, match="hold\\|flatten"):
                NewsGuard(db, dict(NEWS_CFG, position_policy="panic"))

    def test_naive_datetime_rejected(self, guard):
        with pytest.raises(ValueError, match="timezone-aware"):
            guard.is_entry_allowed(datetime(2026, 8, 12, 18, 0))
