from src.reference.contract_resolver import is_tradeable, pick_active, resolve_product
from src.reference.volume_oi import (
    ContractVolumeOI,
    VolumeFetchError,
    month_to_code,
    parse_volume_payload,
)
from src.storage.db import Database

import pytest


def _rec(code, month, volume, oi, product="MES", date="2026-08-14"):
    return ContractVolumeOI(product, code, month, date, volume, oi)


class TestMonthToCode:
    def test_full_year(self):
        assert month_to_code("SEP 2026") == ("U6", "SEP 2026")

    def test_two_digit_year(self):
        assert month_to_code("DEC 26") == ("Z6", "DEC 2026")

    def test_cme_jly_spelling(self):
        code, normalized = month_to_code("JLY 27")
        assert code == "N7"
        assert normalized.endswith("2027")

    def test_garbage_raises(self):
        with pytest.raises(VolumeFetchError):
            month_to_code("???")


class TestParsePayload:
    PAYLOAD = {
        "tradeDate": "2026-08-14",
        "monthData": [
            {"month": "SEP 2026", "totalVolume": "1,204,556", "openInterest": "902,113"},
            {"month": "DEC 2026", "totalVolume": "88,120", "openInterest": "45,900"},
            {"month": "TOTALS", "totalVolume": "1,292,676", "openInterest": "948,013"},
        ],
    }

    def test_parses_rows_and_skips_totals(self):
        records = parse_volume_payload("MES", self.PAYLOAD)
        assert [r.contract_code for r in records] == ["MESU6", "MESZ6"]
        assert records[0].volume == 1204556
        assert records[0].open_interest == 902113
        assert records[0].trade_date == "2026-08-14"

    def test_wordy_trade_date_normalized(self):
        payload = dict(self.PAYLOAD, tradeDate="14 Aug 2026")
        assert parse_volume_payload("MES", payload)[0].trade_date == "2026-08-14"

    def test_empty_payload_raises(self):
        with pytest.raises(VolumeFetchError):
            parse_volume_payload("MES", {"tradeDate": "2026-08-14", "monthData": []})


class TestPickActive:
    def test_volume_and_oi_agree(self):
        winner, agreed = pick_active([
            _rec("MESU6", "SEP 2026", 1_200_000, 900_000),
            _rec("MESZ6", "DEC 2026", 90_000, 50_000),
        ])
        assert winner.contract_code == "MESU6"
        assert agreed

    def test_disagreement_prefers_max_volume(self):
        # roll week: volume already moved to DEC, OI still parked in SEP
        winner, agreed = pick_active([
            _rec("MESU6", "SEP 2026", 500_000, 900_000),
            _rec("MESZ6", "DEC 2026", 700_000, 400_000),
        ])
        assert winner.contract_code == "MESZ6"
        assert not agreed


class TestResolveProduct:
    def test_first_resolution_is_not_a_roll(self, tmp_path):
        with Database(tmp_path / "bot.db") as db:
            res = resolve_product(db, [
                _rec("MESU6", "SEP 2026", 1_200_000, 900_000),
                _rec("MESZ6", "DEC 2026", 90_000, 50_000),
            ])
            assert not res.roll
            assert db.get_active_contract("MES")["contract_code"] == "MESU6"
            history = db.conn.execute(
                "SELECT COUNT(*) FROM volume_oi_history").fetchone()[0]
            assert history == 2

    def test_winner_change_flags_roll(self, tmp_path):
        with Database(tmp_path / "bot.db") as db:
            resolve_product(db, [_rec("MESU6", "SEP 2026", 1_200_000, 900_000)])
            res = resolve_product(db, [
                _rec("MESU6", "SEP 2026", 500_000, 900_000, date="2026-09-10"),
                _rec("MESZ6", "DEC 2026", 700_000, 400_000, date="2026-09-10"),
            ])
            assert res.roll
            row = db.get_active_contract("MES")
            assert row["contract_code"] == "MESZ6"
            assert row["roll_pending"] == 1


class TestStaleness:
    def test_missing_row_is_untradeable(self, tmp_path):
        with Database(tmp_path / "bot.db") as db:
            assert not is_tradeable(db, "MES", stale_after_hours=48)

    def test_fresh_row_is_tradeable(self, tmp_path):
        with Database(tmp_path / "bot.db") as db:
            resolve_product(db, [_rec("MESU6", "SEP 2026", 1, 1)])
            assert is_tradeable(db, "MES", stale_after_hours=48)
