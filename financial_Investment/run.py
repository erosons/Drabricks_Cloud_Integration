#!/usr/bin/env python3
"""
Entry point for the Nigeria Financial Intelligence Dashboard.

Usage:
    python run.py             # cold scrape + scheduler + launch Streamlit
    python run.py --scrape    # run scrapers only (no dashboard)
    python run.py --schedule  # scheduler only (no dashboard, for cron mode)
"""
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-20s] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def _init_and_scrape():
    from storage.database import init_db
    init_db()
    from scheduler import cold_start
    cold_start()


def _start_scheduler():
    from scheduler import start
    sched = start()
    return sched


def _launch_streamlit():
    dashboard = ROOT / "dashboard" / "app.py"
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(dashboard),
        "--server.port", "8501",
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    log.info("Launching Streamlit → http://localhost:8501")
    return subprocess.Popen(cmd, cwd=str(ROOT))


def main():
    args = sys.argv[1:]

    scrape_only   = "--scrape"   in args
    schedule_only = "--schedule" in args

    log.info("=== Nigeria Financial Intelligence System ===")

    # Always init DB and do cold scrape
    log.info("Initialising database and running cold scrape...")
    _init_and_scrape()

    if scrape_only:
        log.info("Scrape-only mode complete. Exiting.")
        return

    # Start background scheduler
    log.info("Starting background scheduler...")
    _start_scheduler()

    if schedule_only:
        log.info("Scheduler running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            from scheduler import stop
            stop()
        return

    # Launch Streamlit
    proc = _launch_streamlit()
    try:
        proc.wait()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        proc.terminate()
        from scheduler import stop
        stop()


if __name__ == "__main__":
    main()
