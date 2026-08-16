"""ForexFactory economic-calendar feed → USD red-folder events (§5).

Uses ForexFactory's machine-readable weekly feed (ff_calendar_thisweek.json,
served from faireconomy.media — verified reachable during development) rather
than scraping the HTML calendar page. Event times arrive with a UTC offset
and are normalized to UTC ISO before storage; the news guard (§5) compares
them against tick timestamps in UTC.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from src.storage.db import Database

log = logging.getLogger("ff_calendar")

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


class CalendarFetchError(Exception):
    pass


@dataclass(frozen=True)
class NewsEvent:
    event_time_utc: str     # ISO, UTC
    title: str
    currency: str           # 'USD'
    impact: str             # 'high' (normalized lowercase)


def parse_feed(items: list[dict], currencies: list[str],
               impacts: list[str]) -> list[NewsEvent]:
    """Filter the raw feed to the configured currencies + impacts and
    normalize timestamps to UTC."""
    wanted_ccy = {c.upper() for c in currencies}
    wanted_impact = {i.lower() for i in impacts}
    events = []
    for item in items:
        currency = str(item.get("country", "")).upper()
        impact = str(item.get("impact", "")).lower()
        if currency not in wanted_ccy or impact not in wanted_impact:
            continue
        raw_date = item.get("date")
        if not raw_date:
            continue
        try:
            when = datetime.fromisoformat(raw_date)
        except ValueError:
            log.warning("unparseable event date %r (%s) — skipped",
                        raw_date, item.get("title"))
            continue
        if when.tzinfo is None:      # feed always carries an offset; be safe
            when = when.replace(tzinfo=timezone.utc)
        events.append(NewsEvent(
            event_time_utc=when.astimezone(timezone.utc).isoformat(),
            title=str(item.get("title", "")).strip(),
            currency=currency,
            impact=impact,
        ))
    return events


def fetch_feed(url: str = FEED_URL, timeout: float = 20.0) -> list[dict]:
    req = urllib.request.Request(url, headers={
        "User-Agent": "tradovate-bot/0.1 reference-daemon"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalendarFetchError(f"calendar feed fetch failed: {exc}") from exc
    if not isinstance(payload, list):
        raise CalendarFetchError("calendar feed was not a JSON list")
    return payload


def refresh_news(db: Database, news_cfg: dict) -> list[NewsEvent]:
    """Daily scrape (§5): fetch, filter, and fully replace news_events.
    On fetch failure the previous scrape is left in place — stale blackout
    windows are safer than none."""
    events = parse_feed(
        fetch_feed(news_cfg.get("feed_url", FEED_URL)),
        currencies=news_cfg["currencies"],
        impacts=news_cfg["impacts"],
    )
    db.replace_news_events(
        [(e.event_time_utc, e.title, e.currency, e.impact) for e in events])
    log.info("news refresh: %d red-folder events stored", len(events))
    return events
