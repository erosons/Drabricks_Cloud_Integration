"""
Global active-trade slot manager.

All pair processes share one JSON file protected by an OS-level
fcntl.flock so reads and writes are atomic across 83 concurrent processes.

A process must acquire a slot before opening a new position and must
release it when the position fully closes.

Env var:
    MAX_ACTIVE_TRADES=5   (0 = unlimited)
"""

import fcntl
import json
import os
from pathlib import Path

from prometheus_client import Gauge

MAX_ACTIVE  = int(os.getenv("MAX_ACTIVE_TRADES", "5"))
_SLOTS_FILE = Path("logs/active_slots.json")
_LOCK_FILE  = Path("logs/active_slots.lock")

active_gauge = Gauge("bot_active_slots", "Pairs currently holding an open position")
max_gauge    = Gauge("bot_max_slots",    "Maximum allowed concurrent open positions")
max_gauge.set(MAX_ACTIVE or 999)


def _load(fh) -> list:
    fh.seek(0)
    raw = fh.read()
    try:
        return json.loads(raw) if raw.strip() else []
    except Exception:
        return []


def _save(fh, active: list) -> None:
    fh.seek(0)
    fh.truncate()
    json.dump(active, fh)
    fh.flush()


def acquire_slot(pair: str) -> bool:
    """
    Claim a slot for *pair* before opening a position.
    Returns True  → slot granted, safe to enter.
    Returns False → cap reached, skip this entry.
    """
    if MAX_ACTIVE == 0:
        return True

    _SLOTS_FILE.parent.mkdir(exist_ok=True)
    with open(_LOCK_FILE, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(_SLOTS_FILE, "a+") as f:
                active = _load(f)
                if pair in active:
                    return True             # already holds slot (re-entry guard)
                if len(active) >= MAX_ACTIVE:
                    active_gauge.set(len(active))
                    return False
                active.append(pair)
                _save(f, active)
                active_gauge.set(len(active))
                return True
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def clear_slots() -> None:
    """Wipe the slots file — called once by launcher at startup."""
    _SLOTS_FILE.parent.mkdir(exist_ok=True)
    with open(_LOCK_FILE, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(_SLOTS_FILE, "w") as f:
                json.dump([], f)
            active_gauge.set(0)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def release_slot(pair: str) -> None:
    """Release the slot for *pair* after position is fully closed."""
    if MAX_ACTIVE == 0:
        return

    _SLOTS_FILE.parent.mkdir(exist_ok=True)
    with open(_LOCK_FILE, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(_SLOTS_FILE, "a+") as f:
                active = _load(f)
                active = [p for p in active if p != pair]
                _save(f, active)
                active_gauge.set(len(active))
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
