"""
APScheduler background jobs. All scrapers run here and persist to SQLite.
"""
import logging
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from config import SCHEDULE, WAT
from storage import database as db

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler = None
_lock = threading.Lock()


# ── Job functions ──────────────────────────────────────────────────────────────

def job_scrape_ngx():
    try:
        from scrapers.ngx import run
        index, equities = run()
        db.insert_ngx_index(index)
        db.insert_ngx_equities(equities)
    except Exception as e:
        log.error("NGX job failed: %s", e)


def job_scrape_cbn():
    try:
        from scrapers.cbn import run
        events = run()
        db.insert_policy_events(events)
    except Exception as e:
        log.error("CBN job failed: %s", e)


def job_scrape_dmo():
    try:
        from scrapers.dmo import run
        rates = run()
        db.insert_treasury_rates(rates)
    except Exception as e:
        log.error("DMO job failed: %s", e)


def job_scrape_funds():
    try:
        from scrapers.fund_managers import run
        rates = run()
        db.insert_fund_rates(rates)
    except Exception as e:
        log.error("Fund managers job failed: %s", e)


def job_scrape_news():
    try:
        from scrapers.news import run
        articles = run()
        db.insert_news(articles)
    except Exception as e:
        log.error("News job failed: %s", e)


def job_scrape_ipo():
    try:
        from scrapers.sec_ng import run
        ipos = run()
        db.insert_ipos(ipos)
    except Exception as e:
        log.error("IPO job failed: %s", e)


def job_opportunity_engine():
    try:
        from processors.opportunity_engine import run
        run()
    except Exception as e:
        log.error("Opportunity engine failed: %s", e)


def job_stock_screener():
    try:
        from processors.stock_screener import run
        picks = run()
        db.upsert_stock_picks(picks)
    except Exception as e:
        log.error("Stock screener failed: %s", e)


def cold_start():
    """Run all scrapers once immediately at startup to populate the DB."""
    log.info("Cold start: running all scrapers...")
    job_scrape_cbn()
    job_scrape_dmo()
    job_scrape_funds()
    job_scrape_news()
    job_scrape_ipo()
    job_scrape_ngx()
    job_opportunity_engine()
    job_stock_screener()
    log.info("Cold start complete.")


# ── Scheduler setup ────────────────────────────────────────────────────────────

def start() -> BackgroundScheduler:
    global _scheduler
    with _lock:
        if _scheduler and _scheduler.running:
            return _scheduler

        _scheduler = BackgroundScheduler(timezone=WAT)

        # NGX: every 15 min, Monday–Friday 9:30am–3pm WAT
        _scheduler.add_job(
            job_scrape_ngx,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour="9-15",
                minute="*/15",
                timezone=WAT,
            ),
            id="ngx",
            name="NGX Equities",
            max_instances=1,
            coalesce=True,
        )

        # CBN: every hour
        _scheduler.add_job(
            job_scrape_cbn,
            trigger=IntervalTrigger(hours=SCHEDULE["cbn_interval_hours"], timezone=WAT),
            id="cbn",
            name="CBN Policy Events",
            max_instances=1,
            coalesce=True,
        )

        # DMO: daily at 8am WAT
        _scheduler.add_job(
            job_scrape_dmo,
            trigger=CronTrigger(hour=SCHEDULE["dmo_cron_hour"], minute=0, timezone=WAT),
            id="dmo",
            name="DMO Treasury Rates",
            max_instances=1,
            coalesce=True,
        )

        # Fund managers: every 6 hours
        _scheduler.add_job(
            job_scrape_funds,
            trigger=IntervalTrigger(hours=SCHEDULE["funds_interval_hours"], timezone=WAT),
            id="funds",
            name="Fund Manager Rates",
            max_instances=1,
            coalesce=True,
        )

        # News: every 30 minutes
        _scheduler.add_job(
            job_scrape_news,
            trigger=IntervalTrigger(minutes=SCHEDULE["news_interval_minutes"], timezone=WAT),
            id="news",
            name="Financial News",
            max_instances=1,
            coalesce=True,
        )

        # IPO: every 6 hours
        _scheduler.add_job(
            job_scrape_ipo,
            trigger=IntervalTrigger(hours=SCHEDULE["ipo_interval_hours"], timezone=WAT),
            id="ipo",
            name="SEC IPO Filings",
            max_instances=1,
            coalesce=True,
        )

        # Opportunity engine: every 30 minutes
        _scheduler.add_job(
            job_opportunity_engine,
            trigger=IntervalTrigger(minutes=SCHEDULE["opportunity_interval_minutes"], timezone=WAT),
            id="opportunities",
            name="Opportunity Engine",
            max_instances=1,
            coalesce=True,
        )

        # Stock screener: every 30 minutes
        _scheduler.add_job(
            job_stock_screener,
            trigger=IntervalTrigger(minutes=30, timezone=WAT),
            id="stock_screener",
            name="NGX Stock Screener",
            max_instances=1,
            coalesce=True,
        )

        _scheduler.start()
        log.info("Scheduler started with %d jobs", len(_scheduler.get_jobs()))
        return _scheduler


def stop():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")
