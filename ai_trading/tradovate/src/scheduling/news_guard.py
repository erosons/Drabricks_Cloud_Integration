"""News blackout guard (§5).

Each stored red-folder event creates a blackout window
[event − before, event + after]:
  * no NEW entries during a blackout
  * working entry orders are cancelled at blackout start
  * open positions: held or flattened per position_policy

Events are read from the news_events table (refreshed daily by the
reference daemon) and cached; call reload() after a refresh, or rely on
the periodic auto-reload.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.storage.db import Database


@dataclass(frozen=True)
class Blackout:
    start: datetime
    end: datetime
    title: str

    def covers(self, now: datetime) -> bool:
        return self.start <= now <= self.end


class NewsGuard:
    def __init__(self, db: Database, news_cfg: dict,
                 reload_every: timedelta = timedelta(minutes=15)):
        self.db = db
        self.enabled = bool(news_cfg.get("enabled", True))
        self.before = timedelta(minutes=int(news_cfg["blackout_before_minutes"]))
        self.after = timedelta(minutes=int(news_cfg["blackout_after_minutes"]))
        self.position_policy = news_cfg.get("position_policy", "hold")
        if self.position_policy not in ("hold", "flatten"):
            raise ValueError(f"news_guard.position_policy must be hold|flatten, "
                             f"got {self.position_policy!r}")
        self._reload_every = reload_every
        self._loaded_at: datetime | None = None
        self._blackouts: list[Blackout] = []

    def reload(self, now: datetime | None = None) -> None:
        self._blackouts = [
            Blackout(
                start=(event := datetime.fromisoformat(row["event_time_utc"]))
                - self.before,
                end=event + self.after,
                title=row["title"],
            )
            for row in self.db.get_news_events()
        ]
        self._loaded_at = now or datetime.now(timezone.utc)

    def _maybe_reload(self, now: datetime) -> None:
        if (self._loaded_at is None
                or now - self._loaded_at >= self._reload_every):
            self.reload(now)

    def active_blackout(self, now: datetime) -> Blackout | None:
        """The blackout covering `now`, or None. `now` must be aware (UTC)."""
        if now.tzinfo is None:
            raise ValueError("NewsGuard requires timezone-aware datetimes")
        if not self.enabled:
            return None
        self._maybe_reload(now)
        for blackout in self._blackouts:
            if blackout.covers(now):
                return blackout
        return None

    def is_entry_allowed(self, now: datetime) -> bool:
        return self.active_blackout(now) is None

    def entering_blackout(self, prev: datetime, now: datetime) -> Blackout | None:
        """The blackout that started between prev and now, if any — the
        moment working entry orders must be cancelled (§5)."""
        current = self.active_blackout(now)
        if current is not None and not current.covers(prev):
            return current
        return None
