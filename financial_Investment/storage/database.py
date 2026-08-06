import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Any

from config import DB_PATH
from storage.models import (
    DDL, NGXIndex, NGXEquity, TreasuryRate, PolicyEvent,
    FundRate, IPO, NewsArticle, Opportunity,
)

log = logging.getLogger(__name__)


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(DDL)
        conn.commit()
    log.info("Database initialised at %s", DB_PATH)


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Writers ──────────────────────────────────────────────────────────────────

def insert_ngx_index(row: NGXIndex) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO ngx_index (timestamp,index_value,change_pct,change_abs,volume,market_cap,deals) "
            "VALUES (?,?,?,?,?,?,?)",
            (row.timestamp, row.index_value, row.change_pct, row.change_abs,
             row.volume, row.market_cap, row.deals),
        )


def insert_ngx_equities(rows: List[NGXEquity]) -> None:
    if not rows:
        return
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO ngx_equities "
            "(timestamp,symbol,name,price,change_pct,change_abs,volume,deals,open_price,high_price,low_price,sector) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r.timestamp, r.symbol, r.name, r.price, r.change_pct, r.change_abs,
              r.volume, r.deals, r.open_price, r.high_price, r.low_price, r.sector)
             for r in rows],
        )
    log.info("Inserted %d NGX equities", len(rows))


def insert_treasury_rates(rows: List[TreasuryRate]) -> None:
    if not rows:
        return
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO treasury_rates (timestamp,instrument,tenor,rate,bid_rate,marginal_rate,source) "
            "VALUES (?,?,?,?,?,?,?)",
            [(r.timestamp, r.instrument, r.tenor, r.rate,
              r.bid_rate, r.marginal_rate, r.source) for r in rows],
        )
    log.info("Inserted %d treasury rates", len(rows))


def insert_policy_event(row: PolicyEvent) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO policy_events (timestamp,event_type,title,value,prev_value,description,url,source) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (row.timestamp, row.event_type, row.title, row.value,
             row.prev_value, row.description, row.url, row.source),
        )


def insert_policy_events(rows: List[PolicyEvent]) -> None:
    for r in rows:
        try:
            insert_policy_event(r)
        except Exception as e:
            log.debug("Skip duplicate policy event: %s", e)


def insert_fund_rates(rows: List[FundRate]) -> None:
    if not rows:
        return
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO fund_rates (timestamp,provider,product,rate,rate_label,currency,duration,min_amount,description) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(r.timestamp, r.provider, r.product, r.rate, r.rate_label,
              r.currency, r.duration, r.min_amount, r.description) for r in rows],
        )
    log.info("Inserted %d fund rates", len(rows))


def insert_ipo(row: IPO) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO ipos "
            "(scraped_at,company,sector,offer_price,units_offered,opening_date,closing_date,listing_date,status,description,source,url) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (row.scraped_at, row.company, row.sector, row.offer_price,
             row.units_offered, row.opening_date, row.closing_date,
             row.listing_date, row.status, row.description, row.source, row.url),
        )


def insert_ipos(rows: List[IPO]) -> None:
    for r in rows:
        try:
            insert_ipo(r)
        except Exception as e:
            log.debug("Skip IPO: %s", e)


def insert_news(rows: List[NewsArticle]) -> None:
    if not rows:
        return
    inserted = 0
    with get_conn() as conn:
        for r in rows:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO news_articles "
                    "(published_at,scraped_at,source,title,summary,url,category,sentiment,tags) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (r.published_at, r.scraped_at, r.source, r.title,
                     r.summary, r.url, r.category, r.sentiment, r.tags),
                )
                inserted += 1
            except Exception as e:
                log.debug("Skip news: %s", e)
    log.info("Inserted %d news articles", inserted)


def insert_opportunity(row: Opportunity) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO opportunities "
            "(detected_at,category,title,description,score,alert_level,source,ref_id,status,expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (row.detected_at, row.category, row.title, row.description,
             row.score, row.alert_level, row.source, row.ref_id,
             row.status, row.expires_at),
        )


# ── Readers ───────────────────────────────────────────────────────────────────

def query(sql: str, params: tuple = ()) -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def latest_ngx_index() -> dict:
    rows = query("SELECT * FROM ngx_index ORDER BY timestamp DESC LIMIT 1")
    return dict(rows[0]) if rows else {}


def ngx_index_history(hours: int = 48) -> List[dict]:
    rows = query(
        "SELECT * FROM ngx_index WHERE timestamp >= datetime('now', ?) ORDER BY timestamp",
        (f"-{hours} hours",),
    )
    return [dict(r) for r in rows]


def latest_equities(limit: int = 200) -> List[dict]:
    rows = query(
        """
        SELECT e.* FROM ngx_equities e
        INNER JOIN (
            SELECT symbol, MAX(timestamp) AS ts FROM ngx_equities GROUP BY symbol
        ) latest ON e.symbol = latest.symbol AND e.timestamp = latest.ts
        ORDER BY ABS(e.change_pct) DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [dict(r) for r in rows]


def latest_treasury_rates() -> List[dict]:
    rows = query(
        """
        SELECT t.* FROM treasury_rates t
        INNER JOIN (
            SELECT instrument, MAX(timestamp) AS ts FROM treasury_rates GROUP BY instrument
        ) latest ON t.instrument = latest.instrument AND t.timestamp = latest.ts
        ORDER BY t.rate DESC
        """,
    )
    return [dict(r) for r in rows]


def treasury_rate_history(instrument: str, days: int = 30) -> List[dict]:
    rows = query(
        "SELECT * FROM treasury_rates WHERE instrument=? AND timestamp >= datetime('now',?) ORDER BY timestamp",
        (instrument, f"-{days} days"),
    )
    return [dict(r) for r in rows]


def latest_fund_rates() -> List[dict]:
    rows = query(
        """
        SELECT f.* FROM fund_rates f
        INNER JOIN (
            SELECT provider, product, MAX(timestamp) AS ts FROM fund_rates GROUP BY provider, product
        ) latest ON f.provider=latest.provider AND f.product=latest.product AND f.timestamp=latest.ts
        ORDER BY f.provider, f.rate DESC
        """,
    )
    return [dict(r) for r in rows]


def latest_policy_events(limit: int = 20) -> List[dict]:
    rows = query(
        "SELECT * FROM policy_events ORDER BY timestamp DESC LIMIT ?", (limit,)
    )
    return [dict(r) for r in rows]


def latest_mpr() -> float:
    rows = query(
        "SELECT value FROM policy_events WHERE event_type='MPR' ORDER BY timestamp DESC LIMIT 1"
    )
    return rows[0]["value"] if rows else 27.5


def open_ipos() -> List[dict]:
    rows = query(
        "SELECT * FROM ipos WHERE status IN ('OPEN','UPCOMING') ORDER BY opening_date"
    )
    return [dict(r) for r in rows]


def all_ipos() -> List[dict]:
    rows = query("SELECT * FROM ipos ORDER BY scraped_at DESC LIMIT 50")
    return [dict(r) for r in rows]


def latest_news(limit: int = 50) -> List[dict]:
    rows = query(
        "SELECT * FROM news_articles ORDER BY published_at DESC LIMIT ?", (limit,)
    )
    return [dict(r) for r in rows]


def active_opportunities() -> List[dict]:
    rows = query(
        "SELECT * FROM opportunities WHERE status='ACTIVE' ORDER BY score DESC LIMIT 30"
    )
    return [dict(r) for r in rows]


def opportunity_counts_by_level() -> dict:
    rows = query(
        "SELECT alert_level, COUNT(*) as cnt FROM opportunities WHERE status='ACTIVE' GROUP BY alert_level"
    )
    return {r["alert_level"]: r["cnt"] for r in rows}


# ── Stock Picks ───────────────────────────────────────────────────────────────

def upsert_stock_picks(picks: List[dict]) -> None:
    """Replace stock_picks with the latest screener run (delete-insert)."""
    if not picks:
        return
    with get_conn() as conn:
        conn.execute("DELETE FROM stock_picks")
        conn.executemany(
            """INSERT INTO stock_picks
               (screened_at, symbol, name, sector, cap_tier, price, change_pct, volume,
                dividend, div_yield_est, price_ref, pe_band, tags, thesis,
                score, recommendation, risk_level, rationale, has_live_price)
               VALUES (:screened_at, :symbol, :name, :sector, :cap_tier, :price, :change_pct, :volume,
                       :dividend, :div_yield_est, :price_ref, :pe_band, :tags, :thesis,
                       :score, :recommendation, :risk_level, :rationale, :has_live_price)""",
            picks,
        )
    log.info("Upserted %d stock picks", len(picks))


def latest_stock_picks(recommendation: str = None, cap_tier: str = None,
                       limit: int = 50) -> List[dict]:
    conditions = []
    params: List = []
    if recommendation:
        conditions.append("recommendation = ?")
        params.append(recommendation)
    if cap_tier:
        conditions.append("cap_tier = ?")
        params.append(cap_tier)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = query(
        f"SELECT * FROM stock_picks {where} ORDER BY score DESC LIMIT ?",
        tuple(params) + (limit,),
    )
    return [dict(r) for r in rows]


def stock_pick_by_symbol(symbol: str) -> dict:
    rows = query("SELECT * FROM stock_picks WHERE symbol = ?", (symbol,))
    return dict(rows[0]) if rows else {}


def stock_picks_summary() -> dict:
    rows = query(
        "SELECT recommendation, COUNT(*) as cnt FROM stock_picks GROUP BY recommendation"
    )
    return {r["recommendation"]: r["cnt"] for r in rows}
