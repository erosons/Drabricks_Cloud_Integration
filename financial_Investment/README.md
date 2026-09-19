# 🇳🇬 Nigeria Financial Intelligence Dashboard

A Grafana-style financial intelligence platform that scrapes Nigerian financial websites, aggregates market data, and surfaces investment opportunities across stocks, treasury instruments, fund managers, IPOs, and government policy moves — all in a single live dashboard.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES (Web)                           │
│                                                                     │
│  NGX Group   CBN   DMO   SEC Nigeria   Nairametrics   BusinessDay  │
│  Rise   PiggyVest   Bamboo   Afriinvest   CowryWise   Proshare    │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP / RSS
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SCRAPER LAYER  (scrapers/)                     │
│                                                                     │
│  ngx.py         → Equity prices, All-Share Index (CSV + HTML)      │
│  cbn.py         → MPR, FX rates, CBN press releases                │
│  dmo.py         → T-Bill rates, FGN Bond yields, Savings Bonds     │
│  sec_ng.py      → IPO filings, public offers                       │
│  fund_managers.py → Rise, PiggyVest, Bamboo, Afriinvest, CowryWise│
│  news.py        → RSS feeds + HTML scrape (30-min cycle)           │
│                                                                     │
│  base.py        → Shared: session, retry logic, SSL fallback       │
└────────────────────────────┬────────────────────────────────────────┘
                             │ Python objects (dataclasses)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     STORAGE LAYER  (storage/)                       │
│                                                                     │
│  SQLite  →  nigeria_finance.db                                     │
│                                                                     │
│  ngx_index       time-series index values                          │
│  ngx_equities    per-symbol OHLCV snapshots                        │
│  treasury_rates  T-Bill / Bond / Savings Bond rates                │
│  policy_events   MPR, CRR, FX rates, press releases                │
│  fund_rates      provider × product × rate × currency              │
│  ipos            company, offer price, dates, status               │
│  news_articles   title, summary, url, category, sentiment          │
│  opportunities   scored investment signals with alert levels        │
└────────────────────────────┬────────────────────────────────────────┘
                             │ SQL queries
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  OPPORTUNITY ENGINE  (processors/)                  │
│                                                                     │
│  Reads latest data → applies 7 signal checks → scores 0–100        │
│                                                                     │
│  HIGH_YIELD_TREASURY  T-Bill rate vs MPR comparison                │
│  POLICY_SHIFT         MPR change detected                          │
│  STOCK_BREAKOUT       Equity ±5% in a session                      │
│  IPO_ALERT            New / open IPO detected                      │
│  FUND_RATE_CHANGE     Provider rate above market average           │
│  GOVT_FISCAL_MOVE     Keyword match in news (budget, eurobond…)    │
│  FX_OPPORTUNITY       USD/NGN rate shift ≥ 1%                      │
│                                                                     │
│  Alert levels: CRITICAL ≥ 80 · HIGH ≥ 60 · MEDIUM ≥ 40 · LOW < 40│
└────────────────────────────┬────────────────────────────────────────┘
                             │
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                 ▼
┌──────────────────┐ ┌─────────────┐ ┌────────────────┐
│  SCHEDULER       │ │  DASHBOARD  │ │  ENTRY POINT   │
│  scheduler.py    │ │  dashboard/ │ │  run.py        │
│                  │ │  app.py     │ │                │
│  APScheduler     │ │             │ │  1. Init DB    │
│  background      │ │  Streamlit  │ │  2. Cold scrape│
│  daemon thread   │ │  dark theme │ │  3. Scheduler  │
│                  │ │  8 panels   │ │  4. Streamlit  │
│  NGX    15 min   │ │  auto-      │ │     :8501      │
│  News   30 min   │ │  refresh    │ └────────────────┘
│  Funds   6 hr    │ │  5 min      │
│  DMO    daily    │ └─────────────┘
└──────────────────┘
```

---

## Project Structure

```
financial_Investment/
├── run.py                      # Entry point — cold scrape + scheduler + Streamlit
├── config.py                   # All URLs, schedule intervals, scoring weights
├── scheduler.py                # APScheduler jobs (background daemon thread)
├── requirements.txt
│
├── scrapers/
│   ├── base.py                 # BaseScraper: retry, SSL fallback, safe parsers
│   ├── ngx.py                  # Nigerian Stock Exchange
│   ├── cbn.py                  # Central Bank of Nigeria
│   ├── dmo.py                  # Debt Management Office
│   ├── sec_ng.py               # Securities & Exchange Commission Nigeria
│   ├── fund_managers.py        # Rise, PiggyVest, Bamboo, Afriinvest, CowryWise
│   └── news.py                 # Nairametrics RSS, BusinessDay RSS, Proshare
│
├── storage/
│   ├── models.py               # Dataclasses + SQLite DDL (CREATE TABLE statements)
│   └── database.py             # init_db(), get_conn(), all readers and writers
│
├── processors/
│   └── opportunity_engine.py   # 7 signal checks → scored Opportunity records
│
├── dashboard/
│   └── app.py                  # Full Streamlit UI — 8 panels, dark theme
│
└── .streamlit/
    └── config.toml             # Dark theme colours, port 8501
```

---

## Data Sources

| Source | What is scraped | Method | Schedule |
|--------|----------------|--------|----------|
| **NGX Group** | All-Share Index, equity prices (OHLCV), gainers/losers | CSV download + HTML parse | Every 15 min (market hours) |
| **CBN** | MPR, CRR, USD/NGN FX rate, press releases | HTML scrape | Every 1 hour |
| **DMO** | 91/182/364-day T-Bill rates, FGN Bond yields (2–30yr), Savings Bond | HTML tables | Daily at 08:00 WAT |
| **SEC Nigeria** | Public offers, IPO status and details | HTML scrape | Every 6 hours |
| **Rise** | USD product rates and descriptions | HTML scrape | Every 6 hours |
| **PiggyVest** | NGN and USD savings rates | HTML scrape | Every 6 hours |
| **Bamboo** | NGN and USD product rates | HTML scrape | Every 6 hours |
| **Afriinvest** | Money Market, Fixed Income, Equity fund rates | HTML scrape | Every 6 hours |
| **CowryWise** | NGN and USD investment rates | HTML scrape | Every 6 hours |
| **Nairametrics** | Financial news headlines + summaries | RSS feed | Every 30 min |
| **BusinessDay NG** | Business and market news | RSS feed | Every 30 min |
| **Proshare** | Market intelligence, analysis | HTML scrape | Every 30 min |

---

## Getting Started

### 1. Install dependencies

```bash
cd financial_Investment
pip install -r requirements.txt
```

### 2. Run the full system

```bash
python run.py
```

This will:
1. Create the SQLite database (`storage/nigeria_finance.db`) with all tables
2. Run a **cold scrape** of all sources immediately
3. Start the **background scheduler** for periodic updates
4. Launch **Streamlit** at `http://localhost:8501`

### 3. Run scrapers only (no dashboard)

```bash
python run.py --scrape
```

Useful for testing data collection or seeding the DB from a cron job.

### 4. Run scheduler only (no dashboard)

```bash
python run.py --schedule
```

Useful for running the scraper daemon separately and pointing a different process at the dashboard.

### 5. Run just the dashboard (data already in DB)

```bash
streamlit run dashboard/app.py
```

---

## Dashboard Panels

### Top KPI Bar
Five metric cards updated on every page load:

| Card | Source |
|------|--------|
| NGX All-Share Index | NGX equities scraper |
| 364-Day T-Bill Rate | DMO |
| CBN MPR (Policy Rate) | CBN |
| USD/NGN Official Rate | CBN |
| Active Opportunity Count | Opportunity engine |

### Panel 1 — NGX Stock Market
- **Line chart**: All-Share Index over the last 48 hours
- **Tabs**: Top Gainers · Top Losers · High Volume — each shows symbol, company, price, change %, volume, sector
- Refreshes during market hours (Mon–Fri, 09:30–15:00 WAT)

### Panel 2 — Treasury & Fixed Income
- **Horizontal bar chart**: All instruments (T-Bills, FGN Bonds, Savings Bonds) vs MPR reference line
- **Table**: Full rate list with source label
- Orange dashed line marks the current CBN MPR for instant comparison

### Panel 3 — Fund Manager Rate Comparison
- **Tabs**: NGN Products · USD Products
- **Bar chart**: All providers side-by-side, coloured by product type
- **Table**: Provider, product, rate %, term, minimum amount, notes
- NGN tab also shows MPR reference line

### Panel 4 — IPO Tracker
- Cards for each OPEN or UPCOMING IPO: status, company, offer price, sector, closing date
- Green border = OPEN, orange border = UPCOMING

### Panel 5 — Government & Policy Alerts
- Scrollable timeline of CBN events: MPR decisions, CRR changes, FX rates, press releases
- Event type, title, value, and timestamp

### Panel 6 — Financial News Feed
- Category filter: ALL · STOCKS · TREASURY · POLICY · FOREX · IPO · GENERAL
- Each article: source, headline (linked), timestamp, sentiment indicator
- Green left border = positive sentiment, red = negative

### Panel 7 — Investment Opportunity Signals
- Summary count row: CRITICAL · HIGH · MEDIUM · LOW
- Signal type filter dropdown
- Each signal: category, alert badge, title, description, score bar (0–100), timestamp

---

## Opportunity Scoring

The engine runs every 30 minutes and produces ranked investment signals.

| Signal | Trigger | Base Score |
|--------|---------|-----------|
| `HIGH_YIELD_TREASURY` | T-Bill rate within 2% of MPR | 30 (+20 if above MPR) |
| `POLICY_SHIFT` | MPR changed from previous reading | 40 (+5 per bp change) |
| `STOCK_BREAKOUT` | Equity moves ±5% in a session | 25 (+2 per extra %) |
| `IPO_ALERT` | Open or upcoming IPO detected | 35 (+15 if status = OPEN) |
| `FUND_RATE_CHANGE` | NGN rate > 20% or USD rate > 8% | 20 (+1 per extra %) |
| `GOVT_FISCAL_MOVE` | Keyword match in news | 25–40 (+ sentiment boost) |
| `FX_OPPORTUNITY` | USD/NGN shifts ≥ 1% | 25 (+3 per extra %) |

Signals expire after 24 hours automatically.

---

## Configuration

All tunable values are in `config.py`:

```python
# Scraping URLs — update here if a site changes structure
SCRAPE_URLS = { "ngx_home": "...", "cbn_home": "...", ... }

# Schedule intervals
SCHEDULE = {
    "ngx_interval_minutes": 15,
    "cbn_interval_hours": 1,
    "dmo_cron_hour": 8,
    "funds_interval_hours": 6,
    "news_interval_minutes": 30,
}

# Opportunity alert level thresholds (0–100 score)
ALERT_THRESHOLDS = { "CRITICAL": 80, "HIGH": 60, "MEDIUM": 40, "LOW": 0 }
```

---

## Extending the System

### Add a new scraper

1. Create `scrapers/your_source.py` extending `BaseScraper`
2. Return a list of dataclass objects from `storage/models.py`
3. Add a write call in `storage/database.py`
4. Register a job in `scheduler.py`

### Add a new opportunity signal

Add a `_check_your_signal(now)` function in `processors/opportunity_engine.py` that returns a list of `Opportunity` objects, then call it inside `run()`.

### Update a dead URL

Edit the relevant key in `SCRAPE_URLS` in `config.py`. Scrapers use `get_first([url1, url2, fallback])` so you can list multiple candidates.

---

## Database

SQLite file: `storage/nigeria_finance.db`

Query it directly:
```bash
sqlite3 storage/nigeria_finance.db

# Latest treasury rates
SELECT instrument, rate, source FROM treasury_rates
WHERE timestamp = (SELECT MAX(timestamp) FROM treasury_rates)
ORDER BY rate DESC;

# Active opportunities
SELECT alert_level, title, score FROM opportunities
WHERE status = 'ACTIVE'
ORDER BY score DESC;

# Recent news
SELECT source, title, published_at FROM news_articles
ORDER BY published_at DESC LIMIT 20;
```

---

## Notes

- **Market hours**: NGX scraper only runs Monday–Friday 09:30–15:00 WAT. Outside those hours the index panel shows the last known values.
- **SSL issues**: Several Nigerian government sites have expired or misconfigured SSL certificates. The base scraper automatically retries without SSL verification when this occurs.
- **Seed data**: DMO and fund manager scrapers include approximate current market rates as seed data. These are used as fallback when live scraping fails and are clearly labelled `[DMO-seed]` in the dashboard.
- **Not financial advice**: This tool is for informational and research purposes only.
