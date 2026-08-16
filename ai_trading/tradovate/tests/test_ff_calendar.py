from src.reference.ff_calendar import NewsEvent, parse_feed, refresh_news
from src.storage.db import Database

# Shape captured from the live feed during development
FEED = [
    {"title": "Bank Lending y/y", "country": "JPY",
     "date": "2026-08-09T19:50:00-04:00", "impact": "Low"},
    {"title": "FOMC Statement", "country": "USD",
     "date": "2026-08-12T14:00:00-04:00", "impact": "High"},
    {"title": "Unemployment Claims", "country": "USD",
     "date": "2026-08-13T08:30:00-04:00", "impact": "Medium"},
    {"title": "CPI m/m", "country": "USD",
     "date": "2026-08-14T08:30:00-04:00", "impact": "High"},
    {"title": "German Prelim GDP q/q", "country": "EUR",
     "date": "2026-08-14T02:00:00-04:00", "impact": "High"},
]


def test_filters_to_usd_high_only():
    events = parse_feed(FEED, currencies=["USD"], impacts=["high"])
    assert [e.title for e in events] == ["FOMC Statement", "CPI m/m"]
    assert all(e.currency == "USD" and e.impact == "high" for e in events)


def test_times_normalized_to_utc():
    events = parse_feed(FEED, currencies=["USD"], impacts=["high"])
    # 14:00 ET (-04:00) == 18:00 UTC
    assert events[0].event_time_utc == "2026-08-12T18:00:00+00:00"


def test_bad_date_skipped_not_fatal():
    feed = FEED + [{"title": "Broken", "country": "USD",
                    "date": "not-a-date", "impact": "High"}]
    events = parse_feed(feed, currencies=["USD"], impacts=["high"])
    assert "Broken" not in [e.title for e in events]
    assert len(events) == 2


def test_refresh_news_replaces_table(tmp_path, monkeypatch):
    import src.reference.ff_calendar as mod
    monkeypatch.setattr(mod, "fetch_feed", lambda url=None: FEED)
    cfg = {"currencies": ["USD"], "impacts": ["high"]}
    with Database(tmp_path / "bot.db") as db:
        db.replace_news_events([("2026-08-01T00:00:00+00:00", "Old", "USD", "high")])
        stored = refresh_news(db, cfg)
        assert len(stored) == 2
        titles = [r["title"] for r in db.get_news_events()]
        assert titles == ["FOMC Statement", "CPI m/m"]   # old scrape gone


def test_daemon_registers_both_jobs(tmp_path):
    from src.config_loader import load_config
    from src.scheduling.reference_daemon import build_scheduler
    from pathlib import Path

    config = load_config(Path(__file__).resolve().parents[1] / "config")
    with Database(tmp_path / "bot.db") as db:
        scheduler = build_scheduler(config, db)
        jobs = {j.id: str(j.trigger) for j in scheduler.get_jobs()}
        assert set(jobs) == {"news_refresh", "volume_oi_refresh"}
        assert "hour='18'" in jobs["news_refresh"]
        assert "minute='30'" in jobs["volume_oi_refresh"]
