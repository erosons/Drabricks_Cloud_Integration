"""SQLite access layer — WAL mode, schema from docs/README.md §20.

Writer discipline (enforced by convention, stated in §20): the reference
daemon is the only writer to reference tables; each product process writes
only its own `fills` rows; the research plane writes only research tables.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
-- ============ execution plane ============

CREATE TABLE IF NOT EXISTS active_contracts (
  product        TEXT PRIMARY KEY,   -- 'MES'
  contract_code  TEXT NOT NULL,      -- 'MESU6'
  contract_month TEXT NOT NULL,      -- 'SEP 2026'
  trade_date     TEXT NOT NULL,      -- CME data date (YYYY-MM-DD)
  volume         INTEGER,
  open_interest  INTEGER,
  roll_pending   INTEGER DEFAULT 0,
  updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS volume_oi_history (
  product TEXT, contract_code TEXT, trade_date TEXT,
  volume INTEGER, open_interest INTEGER,
  PRIMARY KEY (product, contract_code, trade_date)
);

CREATE TABLE IF NOT EXISTS news_events (
  event_time_utc TEXT, title TEXT, currency TEXT, impact TEXT,
  scraped_at TEXT,
  PRIMARY KEY (event_time_utc, title)
);

CREATE TABLE IF NOT EXISTS fills (
  id INTEGER PRIMARY KEY, product TEXT, contract_code TEXT,
  side TEXT, qty INTEGER, price REAL, fee REAL, ts TEXT
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
  ts TEXT PRIMARY KEY, realized_pnl REAL, unrealized_pnl REAL, open_positions TEXT
);

-- Round trips reconstructed from fills: a trip opens on the first fill from
-- flat and closes when the position returns to flat (bought == sold — the
-- engine is one-bracket and never flips through zero). This view is the
-- OF-RECORD source for win/loss stats (Grafana history panels §15); the
-- Prometheus counters are the disposable live view. usd_per_point =
-- tick_value / tick_size per products.yaml — extend the CASE when enabling
-- a product for trading.
DROP VIEW IF EXISTS v_round_trips;
CREATE VIEW v_round_trips AS
WITH running AS (
  SELECT id, product, contract_code, side, qty, price, fee, ts,
         SUM(CASE WHEN side = 'buy' THEN qty ELSE -qty END)
             OVER (PARTITION BY product ORDER BY id) AS pos_after
  FROM fills
), preceded AS (
  SELECT *,
         COALESCE(LAG(pos_after)
                  OVER (PARTITION BY product ORDER BY id), 0) AS pos_before
  FROM running
), tripped AS (
  SELECT *,
         SUM(CASE WHEN pos_before = 0 THEN 1 ELSE 0 END)
             OVER (PARTITION BY product ORDER BY id) AS trip_no
  FROM preceded
)
SELECT product,
       MIN(contract_code)                                    AS contract_code,
       trip_no,
       MIN(ts)                                               AS opened_ts,
       MAX(ts)                                               AS closed_ts,
       SUM(CASE WHEN side = 'buy'  THEN qty ELSE 0 END)      AS bought,
       SUM(CASE WHEN side = 'sell' THEN qty ELSE 0 END)      AS sold,
       SUM(CASE WHEN side = 'buy'  THEN qty ELSE 0 END) =
       SUM(CASE WHEN side = 'sell' THEN qty ELSE 0 END)      AS closed,
       SUM(CASE WHEN side = 'sell' THEN qty * price
                                   ELSE -qty * price END)    AS points_pnl,
       SUM(fee)                                              AS fees,
       CASE product WHEN 'MES' THEN 5.0
                    WHEN 'MNQ' THEN 2.0 END                  AS usd_per_point,
       SUM(CASE WHEN side = 'sell' THEN qty * price
                                   ELSE -qty * price END)
         * CASE product WHEN 'MES' THEN 5.0
                        WHEN 'MNQ' THEN 2.0 END
         - SUM(fee)                                          AS usd_pnl
FROM tripped
GROUP BY product, trip_no;

-- ============ research plane ============

CREATE TABLE IF NOT EXISTS strategy_lifecycle (
  id INTEGER PRIMARY KEY, strategy TEXT, product TEXT,
  state TEXT NOT NULL,               -- idea|limited_test|walk_forward|monte_carlo|
                                     -- incubation|live|retired
  entered_state_at TEXT NOT NULL,
  gate_evidence_run_id INTEGER,      -- FK to the run that justified the transition
  retired_reason TEXT
);

CREATE TABLE IF NOT EXISTS backtest_runs (
  id INTEGER PRIMARY KEY, strategy TEXT, product TEXT, kind TEXT,  -- limited|wf_fold
  params_json TEXT, date_from TEXT, date_to TEXT,
  net_profit REAL, max_drawdown REAL, trades INTEGER,
  largest_loss REAL, fill_flags_json TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS walkforward_folds (
  run_id INTEGER, fold INTEGER, in_from TEXT, in_to TEXT, out_from TEXT, out_to TEXT,
  params_json TEXT, out_net_profit REAL,
  PRIMARY KEY (run_id, fold)
);

CREATE TABLE IF NOT EXISTS monte_carlo_runs (
  id INTEGER PRIMARY KEY, strategy TEXT, product TEXT, source_run_id INTEGER,
  iterations INTEGER, fixed_fraction_x REAL,
  ret_dd_ratio REAL, median_max_dd REAL, p95_max_dd REAL,
  risk_of_ruin REAL, prob_profit_1y REAL,
  cone_json TEXT,                    -- avg / top10 / low10 equity paths
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS incubation_equity (
  strategy TEXT, product TEXT, ts TEXT, paper_pnl REAL, cum_pnl REAL,
  PRIMARY KEY (strategy, product, ts)
);

CREATE TABLE IF NOT EXISTS live_vs_expected (
  strategy TEXT, product TEXT, trade_date TEXT,
  live_cum_pnl REAL, expected_avg REAL, band_low10 REAL, band_top10 REAL,
  quitting_point REAL, breach INTEGER DEFAULT 0,
  PRIMARY KEY (strategy, product, trade_date)
);

CREATE TABLE IF NOT EXISTS reconciliation_log (
  id INTEGER PRIMARY KEY, ts TEXT, product TEXT, check_name TEXT,
  ok INTEGER, detail_json TEXT, acknowledged_at TEXT
);
"""

EXPECTED_TABLES = frozenset({
    "active_contracts", "volume_oi_history", "news_events", "fills",
    "equity_snapshots", "strategy_lifecycle", "backtest_runs",
    "walkforward_folds", "monte_carlo_runs", "incubation_equity",
    "live_vs_expected", "reconciliation_log",
})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """One connection per process. WAL mode so the reference daemon, product
    processes, and the research plane can read concurrently."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)  # autocommit
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- reference tables (reference daemon is the sole writer) ----

    def upsert_active_contract(self, product: str, contract_code: str,
                               contract_month: str, trade_date: str,
                               volume: int | None, open_interest: int | None,
                               roll_pending: bool = False) -> None:
        self.conn.execute(
            """INSERT INTO active_contracts
               (product, contract_code, contract_month, trade_date,
                volume, open_interest, roll_pending, updated_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(product) DO UPDATE SET
                 contract_code=excluded.contract_code,
                 contract_month=excluded.contract_month,
                 trade_date=excluded.trade_date,
                 volume=excluded.volume,
                 open_interest=excluded.open_interest,
                 roll_pending=excluded.roll_pending,
                 updated_at=excluded.updated_at""",
            (product, contract_code, contract_month, trade_date,
             volume, open_interest, int(roll_pending), utc_now_iso()),
        )

    def get_active_contract(self, product: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM active_contracts WHERE product=?", (product,)
        ).fetchone()

    def active_contract_age_hours(self, product: str) -> float | None:
        """Hours since the active-contract row was last refreshed; None if no
        row exists. Used for the resolver's stale_after_hours refusal (§4)."""
        row = self.get_active_contract(product)
        if row is None:
            return None
        updated = datetime.fromisoformat(row["updated_at"])
        return (datetime.now(timezone.utc) - updated).total_seconds() / 3600.0

    def insert_volume_oi(self, product: str, contract_code: str,
                         trade_date: str, volume: int, open_interest: int) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO volume_oi_history
               (product, contract_code, trade_date, volume, open_interest)
               VALUES (?,?,?,?,?)""",
            (product, contract_code, trade_date, volume, open_interest),
        )

    def replace_news_events(self, events: list[tuple[str, str, str, str]]) -> None:
        """events: (event_time_utc, title, currency, impact). Full refresh —
        the daily scrape is authoritative for the coming session."""
        now = utc_now_iso()
        with self.conn:  # single transaction
            self.conn.execute("DELETE FROM news_events")
            self.conn.executemany(
                "INSERT OR REPLACE INTO news_events VALUES (?,?,?,?,?)",
                [(t, title, cur, imp, now) for (t, title, cur, imp) in events],
            )

    def get_news_events(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM news_events ORDER BY event_time_utc"
        ).fetchall()

    # ---- execution plane (each product process writes only its own rows) ----

    def record_fill(self, product: str, contract_code: str, side: str,
                    qty: int, price: float, fee: float) -> int:
        cur = self.conn.execute(
            "INSERT INTO fills (product, contract_code, side, qty, price, fee, ts)"
            " VALUES (?,?,?,?,?,?,?)",
            (product, contract_code, side, qty, price, fee, utc_now_iso()),
        )
        return cur.lastrowid

    def snapshot_equity(self, realized_pnl: float, unrealized_pnl: float,
                        open_positions_json: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO equity_snapshots VALUES (?,?,?,?)",
            (utc_now_iso(), realized_pnl, unrealized_pnl, open_positions_json),
        )
