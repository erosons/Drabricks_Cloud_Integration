from datetime import datetime, timedelta, timezone

from src.storage.db import EXPECTED_TABLES, Database


def test_schema_created_with_wal(tmp_path):
    with Database(tmp_path / "bot.db") as db:
        mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        tables = {r["name"] for r in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert EXPECTED_TABLES <= tables


def test_active_contract_upsert_and_staleness(tmp_path):
    with Database(tmp_path / "bot.db") as db:
        assert db.get_active_contract("MES") is None
        assert db.active_contract_age_hours("MES") is None

        db.upsert_active_contract("MES", "MESU6", "SEP 2026", "2026-08-14",
                                  volume=1_200_000, open_interest=900_000)
        row = db.get_active_contract("MES")
        assert row["contract_code"] == "MESU6"
        assert row["roll_pending"] == 0
        assert db.active_contract_age_hours("MES") < 0.1

        # roll: same product key, new month
        db.upsert_active_contract("MES", "MESZ6", "DEC 2026", "2026-09-10",
                                  volume=1_500_000, open_interest=950_000,
                                  roll_pending=True)
        row = db.get_active_contract("MES")
        assert row["contract_code"] == "MESZ6"
        assert row["roll_pending"] == 1
        assert db.conn.execute(
            "SELECT COUNT(*) FROM active_contracts").fetchone()[0] == 1

    # staleness math against an old timestamp
    with Database(tmp_path / "bot.db") as db:
        old = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        db.conn.execute(
            "UPDATE active_contracts SET updated_at=? WHERE product='MES'", (old,))
        assert db.active_contract_age_hours("MES") > 48


def test_news_events_full_refresh(tmp_path):
    with Database(tmp_path / "bot.db") as db:
        db.replace_news_events([
            ("2026-08-19T18:00:00+00:00", "FOMC Statement", "USD", "high"),
            ("2026-08-21T12:30:00+00:00", "Non-Farm Payrolls", "USD", "high"),
        ])
        assert len(db.get_news_events()) == 2

        db.replace_news_events([
            ("2026-08-22T12:30:00+00:00", "CPI m/m", "USD", "high"),
        ])
        events = db.get_news_events()
        assert len(events) == 1                    # old scrape fully replaced
        assert events[0]["title"] == "CPI m/m"


def test_fills_and_equity(tmp_path):
    with Database(tmp_path / "bot.db") as db:
        fill_id = db.record_fill("YM", "YMU6", "buy", 1, 40000.0, 2.50)
        assert fill_id == 1
        db.snapshot_equity(150.0, -25.0, '{"YM": 1}')
        assert db.conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1
        assert db.conn.execute(
            "SELECT realized_pnl FROM equity_snapshots").fetchone()[0] == 150.0
