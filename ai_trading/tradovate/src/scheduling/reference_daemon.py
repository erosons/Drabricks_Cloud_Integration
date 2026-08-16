"""Reference daemon — the ONE process that writes reference tables (§20).

APScheduler cron jobs, America/New_York:
  * news_guard.refresh_time_et      (18:00) → ForexFactory calendar refresh
  * contract_resolver.refresh_time_et (18:30) → CME volume/OI + active month

Run:  python -m src.scheduling.reference_daemon [--config-dir config] [--now]
      (--now fires both jobs immediately once, then keeps the schedule)
"""

from __future__ import annotations

import argparse
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config_loader import AppConfig, load_config
from src.reference import contract_resolver, ff_calendar
from src.storage.db import Database

log = logging.getLogger("reference_daemon")

ET = "America/New_York"


def _hhmm(value: str) -> tuple[int, int]:
    hour, minute = value.strip().split(":")
    return int(hour), int(minute)


def build_scheduler(config: AppConfig, db: Database) -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=ET)

    news_cfg = config.raw["news_guard"]
    if news_cfg.get("enabled", True):
        hour, minute = _hhmm(news_cfg["refresh_time_et"])
        scheduler.add_job(
            lambda: ff_calendar.refresh_news(db, news_cfg),
            CronTrigger(hour=hour, minute=minute, timezone=ET),
            id="news_refresh", name="ForexFactory calendar refresh",
            misfire_grace_time=3600,
        )

    hour, minute = _hhmm(config.raw["contract_resolver"]["refresh_time_et"])
    scheduler.add_job(
        lambda: contract_resolver.run_once(config, db),
        CronTrigger(hour=hour, minute=minute, timezone=ET),
        id="volume_oi_refresh", name="CME volume/OI + active-contract resolve",
        misfire_grace_time=3600,
    )
    return scheduler


def main() -> int:
    parser = argparse.ArgumentParser(description="Reference-data daemon")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--now", action="store_true",
                        help="run both jobs immediately, then keep schedule")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = load_config(args.config_dir)
    db = Database(config.raw["database"]["path"])
    scheduler = build_scheduler(config, db)

    if args.now:
        for job in scheduler.get_jobs():
            log.info("--now: firing %s", job.id)
            try:
                job.func()
            except Exception:
                log.exception("%s failed", job.id)

    log.info("reference daemon up: %s",
             ", ".join(f"{j.id}@{j.trigger}" for j in scheduler.get_jobs()))
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
