"""Pull historical CME data from Databento into data/databento/, via batch jobs.

Submits one server-side batch job per (schema, range), refuses to submit
if the quoted cost is not $0 (i.e. the request falls outside what the
active subscription covers), polls until the jobs finish, and downloads
the files. DBN + zstd, split monthly. Safe to re-run: a completed job is
just re-downloaded, not re-billed.

    python scripts/fetch_history.py                 # default backtest set (MES)
    python scripts/fetch_history.py --symbol MNQ.v.0

Default set:
  tbbo    1 year   (trades + BBO at trade time — quadrant-trail backtests)
  mbp-10  1 month  (depth study: imbalance(10) vs imbalance(1))

Reads DATABENTO_API_KEY from the environment or ../.env.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import databento as db

from src.utils.logger import get_logger

log = get_logger("fetch_history")

DATASET = "GLBX.MDP3"
DEFAULT_JOBS = [
    # (schema, start, end)
    ("tbbo", "2025-08-20", "2026-08-19"),
    ("mbp-10", "2026-07-19", "2026-08-19"),
]


def load_key() -> str:
    key = os.environ.get("DATABENTO_API_KEY")
    if not key and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("DATABENTO_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        sys.exit("DATABENTO_API_KEY not set (env or .env)")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description="pull Databento history")
    parser.add_argument("--symbol", default="MES.v.0",
                        help="continuous symbol (default MES.v.0)")
    parser.add_argument("--out", default=str(ROOT / "data" / "databento"))
    parser.add_argument("--poll", type=int, default=30,
                        help="seconds between job-state polls")
    args = parser.parse_args()

    client = db.Historical(load_key())
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    submitted: dict[str, str] = {}  # job_id -> label
    for schema, start, end in DEFAULT_JOBS:
        label = f"{args.symbol} {schema} {start}..{end}"
        cost = client.metadata.get_cost(
            dataset=DATASET, symbols=[args.symbol], schema=schema,
            start=start, end=end, stype_in="continuous")
        if cost > 0.005:
            log.error("REFUSING %s: quoted $%.2f, not covered by the "
                      "subscription — narrow the range or check the plan",
                      label, cost)
            return 2
        job = client.batch.submit_job(
            dataset=DATASET, symbols=[args.symbol], schema=schema,
            start=start, end=end, stype_in="continuous",
            encoding="dbn", compression="zstd", split_duration="month")
        submitted[job["id"]] = label
        log.info("submitted %s → job %s ($0.00)", label, job["id"])

    pending = set(submitted)
    while pending:
        time.sleep(args.poll)
        states = {j["id"]: j["state"]
                  for j in client.batch.list_jobs()
                  if j["id"] in pending}
        for job_id, state in states.items():
            if state == "done":
                log.info("job %s (%s) done — downloading…",
                         job_id, submitted[job_id])
                files = client.batch.download(
                    job_id=job_id, output_dir=out_dir)
                total = sum(f.stat().st_size for f in files)
                log.info("downloaded %d files, %.2f GB → %s",
                         len(files), total / 1e9, out_dir / job_id)
                pending.discard(job_id)
            elif state == "expired":
                log.error("job %s (%s) expired before download",
                          job_id, submitted[job_id])
                pending.discard(job_id)
            else:
                log.info("job %s (%s): %s", job_id, submitted[job_id], state)

    log.info("all jobs finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
