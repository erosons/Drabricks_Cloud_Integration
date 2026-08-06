"""
Minimal cron-like runner for market_scanner_once.
Calls main() every INTERVAL_SEC seconds, then sleeps.
No persistent state — equivalent to: */5 * * * * python market_scanner_once.py
"""

import time
import traceback
import signal
import sys

import market_scanner_once as scanner

INTERVAL_SEC = 300  # 5 minutes

_stop = False


def _handle_signal(sig, frame):
    global _stop
    _stop = True
    print("\n[scanner_cron] Shutting down.", flush=True)
    sys.exit(0)


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

if __name__ == "__main__":
    print(f"[scanner_cron] Started — running every {INTERVAL_SEC}s", flush=True)
    while not _stop:
        try:
            scanner.main()
        except Exception:
            traceback.print_exc()
        next_run = time.time() + INTERVAL_SEC
        while not _stop and time.time() < next_run:
            time.sleep(1)
