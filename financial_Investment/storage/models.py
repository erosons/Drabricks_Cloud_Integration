from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

DDL = """
CREATE TABLE IF NOT EXISTS ngx_index (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   DATETIME NOT NULL,
    index_value REAL,
    change_pct  REAL,
    change_abs  REAL,
    volume      REAL,
    market_cap  REAL,
    deals       INTEGER
);

CREATE TABLE IF NOT EXISTS ngx_equities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   DATETIME NOT NULL,
    symbol      TEXT NOT NULL,
    name        TEXT,
    price       REAL,
    change_pct  REAL,
    change_abs  REAL,
    volume      INTEGER,
    deals       INTEGER,
    open_price  REAL,
    high_price  REAL,
    low_price   REAL,
    sector      TEXT
);

CREATE TABLE IF NOT EXISTS treasury_rates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   DATETIME NOT NULL,
    instrument  TEXT NOT NULL,
    tenor       TEXT,
    rate        REAL NOT NULL,
    bid_rate    REAL,
    marginal_rate REAL,
    source      TEXT
);

CREATE TABLE IF NOT EXISTS policy_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   DATETIME NOT NULL,
    event_type  TEXT NOT NULL,
    title       TEXT NOT NULL,
    value       REAL,
    prev_value  REAL,
    description TEXT,
    url         TEXT,
    source      TEXT
);

CREATE TABLE IF NOT EXISTS fund_rates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   DATETIME NOT NULL,
    provider    TEXT NOT NULL,
    product     TEXT NOT NULL,
    rate        REAL,
    rate_label  TEXT,
    currency    TEXT DEFAULT 'NGN',
    duration    TEXT,
    min_amount  REAL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS ipos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scraped_at      DATETIME NOT NULL,
    company         TEXT NOT NULL,
    sector          TEXT,
    offer_price     REAL,
    units_offered   TEXT,
    opening_date    TEXT,
    closing_date    TEXT,
    listing_date    TEXT,
    status          TEXT DEFAULT 'UPCOMING',
    description     TEXT,
    source          TEXT,
    url             TEXT,
    UNIQUE(company, opening_date)
);

CREATE TABLE IF NOT EXISTS news_articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    published_at DATETIME,
    scraped_at  DATETIME NOT NULL,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    summary     TEXT,
    url         TEXT UNIQUE,
    category    TEXT DEFAULT 'GENERAL',
    sentiment   REAL DEFAULT 0.0,
    tags        TEXT
);

CREATE TABLE IF NOT EXISTS opportunities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at DATETIME NOT NULL,
    category    TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    score       REAL DEFAULT 0.0,
    alert_level TEXT DEFAULT 'LOW',
    source      TEXT,
    ref_id      INTEGER,
    status      TEXT DEFAULT 'ACTIVE',
    expires_at  DATETIME
);

CREATE TABLE IF NOT EXISTS stock_picks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    screened_at     DATETIME NOT NULL,
    symbol          TEXT NOT NULL,
    name            TEXT,
    sector          TEXT,
    cap_tier        TEXT,
    price           REAL,
    change_pct      REAL,
    volume          INTEGER,
    dividend        INTEGER DEFAULT 0,
    div_yield_est   REAL DEFAULT 0,
    price_ref       TEXT,
    pe_band         TEXT,
    tags            TEXT,
    thesis          TEXT,
    score           REAL DEFAULT 0,
    recommendation  TEXT,
    risk_level      TEXT,
    rationale       TEXT,
    has_live_price  INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_stock_picks_ts  ON stock_picks(screened_at);
CREATE INDEX IF NOT EXISTS idx_stock_picks_sym ON stock_picks(symbol);

CREATE INDEX IF NOT EXISTS idx_ngx_index_ts     ON ngx_index(timestamp);
CREATE INDEX IF NOT EXISTS idx_ngx_eq_ts        ON ngx_equities(timestamp);
CREATE INDEX IF NOT EXISTS idx_ngx_eq_symbol    ON ngx_equities(symbol);
CREATE INDEX IF NOT EXISTS idx_treasury_ts      ON treasury_rates(timestamp);
CREATE INDEX IF NOT EXISTS idx_policy_ts        ON policy_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_fund_rates_ts    ON fund_rates(timestamp);
CREATE INDEX IF NOT EXISTS idx_news_pub         ON news_articles(published_at);
CREATE INDEX IF NOT EXISTS idx_opps_detected    ON opportunities(detected_at);
CREATE INDEX IF NOT EXISTS idx_opps_status      ON opportunities(status);
"""


@dataclass
class NGXIndex:
    timestamp: datetime
    index_value: float = 0.0
    change_pct: float = 0.0
    change_abs: float = 0.0
    volume: float = 0.0
    market_cap: float = 0.0
    deals: int = 0


@dataclass
class NGXEquity:
    timestamp: datetime
    symbol: str
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    change_abs: float = 0.0
    volume: int = 0
    deals: int = 0
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    sector: str = ""


@dataclass
class TreasuryRate:
    timestamp: datetime
    instrument: str
    rate: float
    tenor: str = ""
    bid_rate: Optional[float] = None
    marginal_rate: Optional[float] = None
    source: str = "DMO"


@dataclass
class PolicyEvent:
    timestamp: datetime
    event_type: str
    title: str
    value: Optional[float] = None
    prev_value: Optional[float] = None
    description: str = ""
    url: str = ""
    source: str = "CBN"


@dataclass
class FundRate:
    timestamp: datetime
    provider: str
    product: str
    rate: Optional[float] = None
    rate_label: str = ""
    currency: str = "NGN"
    duration: str = ""
    min_amount: Optional[float] = None
    description: str = ""
    source_url: str = ""  # not persisted, used during scraping only


@dataclass
class IPO:
    scraped_at: datetime
    company: str
    sector: str = ""
    offer_price: Optional[float] = None
    units_offered: str = ""
    opening_date: str = ""
    closing_date: str = ""
    listing_date: str = ""
    status: str = "UPCOMING"
    description: str = ""
    source: str = "SEC"
    url: str = ""


@dataclass
class NewsArticle:
    scraped_at: datetime
    source: str
    title: str
    summary: str = ""
    url: str = ""
    published_at: Optional[datetime] = None
    category: str = "GENERAL"
    sentiment: float = 0.0
    tags: str = ""


@dataclass
class Opportunity:
    detected_at: datetime
    category: str
    title: str
    description: str = ""
    score: float = 0.0
    alert_level: str = "LOW"
    source: str = ""
    ref_id: Optional[int] = None
    status: str = "ACTIVE"
    expires_at: Optional[datetime] = None
