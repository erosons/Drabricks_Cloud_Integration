# Tradovate CME Futures AI Trading Bot — Architecture Design

A multi-product, fully-async **futures** trading bot for CME Globex markets, executed
through the [Tradovate](https://tradovate.com) API. It ports the order-flow /
EMA-trend / V-exhaustion engine from the sibling `kraken_ai_trading` bot and adds the
three subsystems futures require that spot crypto does not:

1. **Active-contract resolution** — daily CME Volume & Open Interest pull to know
   which contract month is the live one (and when to roll).
2. **Economic news guard** — ForexFactory "red-folder" USD events create no-trade
   blackout windows (15 min before → 15 min after).
3. **Session management** — futures have a maintenance break; the bot trades
   the 08:00 ET → 16:00 ET day session, then flattens everything and goes quiet.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [The Three-Switch Safety Model](#2-the-three-switch-safety-model)
3. [Product Universe](#3-product-universe)
4. [Component Map](#4-component-map)
5. [Active-Contract Resolver](#5-active-contract-resolver)
6. [News Guard](#6-news-guard)
7. [Session Manager](#7-session-manager)
8. [Trade Decision Pipeline](#8-trade-decision-pipeline)
9. [Directory Structure](#9-directory-structure)
10. [Database Schema](#10-database-schema)
11. [Configuration Reference](#11-configuration-reference)
12. [Risk Management](#12-risk-management)
13. [Monitoring](#13-monitoring)
14. [Build Roadmap](#14-build-roadmap)

---

## 1. Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                            launcher.py                                 │
│                  (spawns one process per product with                  │
│                       trade: true in products.yaml)                    │
│                                                                        │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐              │
│   │ MES Process  │   │ MNQ Process  │   │ MCL Process  │   ...        │
│   │ main.py MES  │   │ main.py MNQ  │   │ main.py MCL  │              │
│   │ port :8101   │   │ port :8102   │   │ port :8103   │              │
│   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘              │
│          └──────────────────┼──────────────────┘                      │
│                             │ reads                                   │
│   ┌─────────────────────────▼──────────────────────────┐             │
│   │              SQLite  data/tradovate_bot.db          │             │
│   │  active_contracts │ news_events │ fills │ vol_oi    │             │
│   └─────────────────────────▲──────────────────────────┘             │
│                             │ writes (daily jobs)                     │
│   ┌─────────────────────────┴──────────────────────────┐             │
│   │            reference_daemon.py (scheduler)          │             │
│   │                                                     │             │
│   │  18:00 ET  ForexFactory calendar scrape (USD, red)  │             │
│   │  18:30 ET  CME Volume & OI pull → active contracts  │             │
│   └────────────────────────────────────────────────────┘             │
└────────────────────────────────────────────────────────────────────────┘
          │                          │
          ▼                          ▼
┌─────────────────────────┐  ┌──────────────────────────────────────────┐
│  Tradovate REST + WS    │  │  Reference sources (HTTP, daily)          │
│                         │  │                                          │
│  auth: accessTokenRequest│ │  cmegroup.com/markets/<slug>/volume       │
│  orders: placeOrder,    │  │  forexfactory.com/calendar                │
│    cancelOrder, liquidate│ └──────────────────────────────────────────┘
│  md: wss://md.tradovate…│
│  demo vs live URL picked │
│  by mode switches        │
└─────────────────────────┘
```

### Key Design Decisions (inherited + new)

| Decision | Rationale |
|----------|-----------|
| **Process-per-product isolation** | Same as kraken bot: one crash never kills the fleet; tune/restart one product independently |
| **Shared reference daemon** | Volume/OI and the news calendar are account-wide facts — scraped once, stored in SQLite, read by every product process. Avoids 30 processes hammering CME/ForexFactory |
| **SQLite as the contract of record** | Product processes never scrape; they only read `active_contracts` and `news_events`. If reference data is stale (> 48 h) the process refuses to trade |
| **Three-switch safety model** | `dry_run`, `live_trading`, per-product `trade` — see §2. Live orders require two deliberate flips plus a product opt-in |
| **Tick-native math** | All prices quantized to `tick_size`; all risk converted USD → ticks via `tick_value`. No floating-point price drift on order placement |
| **Flatten-at-close is unconditional** | The 15:55 ET flatten runs even if strategy/news modules are wedged — it is a top-level watchdog, not a strategy behavior |

---

## 2. The Three-Switch Safety Model

All three live in config (`config/config.yaml` + `config/products.yaml`):

```
mode.dry_run        mode.live_trading        products.<SYM>.trade
     │                      │                        │
     ▼                      ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ dry_run=true                → signals logged, NO orders at all  │
│ dry_run=false, live=false   → orders to Tradovate DEMO account  │
│ dry_run=false, live=true    → orders to Tradovate LIVE account  │
│                                                                 │
│ In every mode, only products with trade: true are launched.     │
└─────────────────────────────────────────────────────────────────┘
```

To go live a user must deliberately: set `dry_run: false`, set `live_trading: true`,
and set `trade: true` on each product they want traded. Everything else in the
catalog stays inert. The launcher prints a red banner and requires `--confirm-live`
on the command line when both live switches are set — a fourth, non-config gate.

---

## 3. Product Universe

The full catalog lives in [`config/products.yaml`](../config/products.yaml) — every
CME **mini and micro** future across the seven CME product groups, each with
exchange, contract size, tick size/value, listed months, CME volume-page slug, and
its `trade` flag.

| Category | Micro | Mini |
|----------|-------|------|
| **Equities** | MES (Micro S&P 500), MNQ (Micro Nasdaq-100), MYM (Micro Dow), M2K (Micro Russell 2000) | ES, NQ, YM, RTY, EMD (S&P MidCap 400) |
| **Energy** | MCL (Micro WTI Crude), MNG (Micro Henry Hub NatGas) | QM (E-mini Crude), QG (E-mini NatGas) |
| **Metals** | MGC (Micro Gold), SIL (Micro Silver 1000 oz), MHG (Micro Copper) | QO (E-mini Gold), QI (E-mini Silver) |
| **FX** | M6E (EUR), M6B (GBP), M6A (AUD), MCD (CAD), MJY (JPY), MSF (CHF) | E7 (E-mini Euro), J7 (E-mini Yen) |
| **Interest Rates** | 2YY, 5YY, 10Y, 30Y (Micro Treasury Yields — $10/bp) | *(no mini tier exists)* |
| **Crypto** | MBT (Micro Bitcoin), MET (Micro Ether), MSL (Micro Solana), MXP (Micro XRP) | *(full-size only above micro)* |
| **Agriculture** | MZC (Micro Corn), MZW (Micro Wheat), MZS (Micro Soybean), MZL (Micro Bean Oil), MZM (Micro Bean Meal) | XC (Mini Corn), XW (Mini Wheat), XK (Mini Soybean) |

Notes:
- Interest rates have no mini tier; the micro tier is the cash-settled Micro
  Treasury Yield suite (quoted in yield, not price).
- Micro Ag launched Feb 2025 (1/10 standard size); minis are 1/5 standard.
- Crypto micros MSL (Solana) and MXP (XRP) launched in 2025.

---

## 4. Component Map

```
src/
├── auth/
│   └── tradovate_auth.py ──── accessTokenRequest + renewal loop (~60 min),
│                              demo/live endpoint selection from mode switches
├── client/
│   ├── rest.py ────────────── Async REST: accounts, placeOrder, cancelOrder,
│   │                          liquidatePosition, cancelAllOrders
│   └── websocket.py ───────── Auto-reconnect WS (Tradovate frame protocol:
│                              open/heartbeat 'h' frames, JSON arrays)
├── reference/
│   ├── volume_oi.py ───────── CME Volume & OI fetcher (per product slug)
│   ├── contract_resolver.py ─ picks active month, writes active_contracts,
│   │                          flags rolls
│   └── ff_calendar.py ─────── ForexFactory scraper → USD red-folder events
├── scheduling/
│   ├── reference_daemon.py ── APScheduler: 18:00 ET calendar, 18:30 ET vol/OI
│   ├── session_manager.py ─── open/close/flatten state machine (§7)
│   └── news_guard.py ──────── blackout window evaluation on every tick (§6)
├── market_data/
│   ├── orderbook.py ───────── DOM (depth-of-market) book, tick-indexed
│   └── ticker.py ──────────── quote/settlement snapshot
├── trading/
│   ├── signals.py ─────────── Signal enum: BUY / SELL / NEUTRAL   (ported)
│   ├── orders.py ──────────── Order model + Tradovate OrderManager
│   ├── position.py ────────── net position, avg px, realized/unrealized P&L
│   ├── risk.py ────────────── tick-native progressive trailing SL/TP (ported)
│   ├── price_action.py ────── EMA trend + V-bottom/V-top + re-test  (ported)
│   └── order_flow.py ──────── strategy engine / central event hub  (ported)
├── storage/
│   └── db.py ──────────────── SQLite access layer (WAL mode, one writer)
└── utils/
    ├── logger.py ──────────── structured logging, [SYMBOL] prefix
    └── metrics.py ─────────── Prometheus gauges/counters per product
```

The four `(ported)` modules keep their kraken logic; only their price arithmetic
changes (percent-based thresholds → tick-based where marked in config).

---

## 5. Active-Contract Resolver

Futures trade in monthly/quarterly contracts; the bot must always know which
expiry is the *active* one (e.g. is Micro S&P currently `MESU6` or `MESZ6`?).

```
Daily 18:30 ET (after CME publishes final prior-day volume):

for each product with trade: true:
    GET https://www.cmegroup.com/markets/{cme_slug}/volume
        (underlying JSON endpoint discovered from the page; falls back to
         HTML table parse — e.g. corn:
         /markets/agriculture/grains/corn/volume#tradeDate=YYYYMMDD)
         │
         ▼
    rows: [{month: SEP 26, volume: 1_412_003, open_interest: 2_103_446}, …]
         │
         ▼
    active = month with MAX volume  AND  MAX open interest
             (if they disagree → prefer max volume, log a ROLL-WATCH warning)
         │
         ▼
    UPSERT active_contracts (product, contract_code, trade_date, volume, oi)
    INSERT volume_oi_history (full table, for roll analytics)
         │
         ▼
    if active != yesterday's active:
        mark roll_pending — product process finishes today's session on the
        old month, then subscribes to the new month at the next session open
```

**Guard**: a product process refuses to enter trades if its `active_contracts`
row is older than `stale_after_hours` (48 h) — stale reference data means we
might be quoting a dying contract.

---

## 6. News Guard

```
Daily 18:00 ET:
    GET https://www.forexfactory.com/calendar        (today + tomorrow)
    filter: currency == USD  AND  impact == High (red folder)
    → INSERT news_events (event_time_utc, title, currency, impact)

Runtime (evaluated in the strategy loop, per tick):

                 event−15m           event            event+15m
    ─────────────────┬─────────────────┬─────────────────┬──────────────
      normal trading │    BLACKOUT     │    BLACKOUT     │ normal trading
                     │                 │                 │
    at blackout start:                                   at blackout end:
    ├── cancel working entry orders                      └── resume signals
    ├── suppress all new signals
    └── open positions: position_policy
        ├── hold    → keep position, SL/TP still active (default)
        └── flatten → liquidate before the event
```

Typical red-folder USD events this catches: CPI, NFP, FOMC rate decision,
GDP, PPI, retail sales, Fed chair speeches.

**Failure mode**: if the calendar scrape fails, the bot keeps the *last
successful* day's events and logs `NEWS-GUARD DEGRADED`; if data is older than
24 h and `news_guard.enabled: true`, new entries are suppressed entirely
(fail-closed, configurable).

---

## 7. Session Manager

CME Globex trades nearly 23 h/day, but this bot deliberately trades a narrower
window and is always flat through the maintenance break:

```
        ET  16:00                        08:00              15:55    16:00
  ───────────┼─────────── ... ────────────┼──────────────────┼────────┼───►
             │          CLOSED            │       OPEN       │FLATTEN │
             │     (no orders, flat)      │    (trading)     │        │
             │                            │                  │        │
                              08:00 ET  session open:   15:55 ET  FLATTEN_ALL:
                              ├── re-read active_contracts   ├── cancel every
                              ├── (apply pending roll)       │   working order
                              ├── subscribe MD for           ├── liquidate every
                              │   active month               │   open position
                              └── begin EMA warmup           └── verify flat via
                                                                 REST poll — retry
                                                                 until confirmed

  Trade days: Monday–Friday, 08:00 → 16:00 ET day session.
  (Sunday is listed in trade_days for forward-compat, but the 08:00–16:00
  window never overlaps Globex's Sunday 18:00 ET open, so no Sunday trading.)
  Saturday: fully closed.
```

State machine: `CLOSED → OPEN → FLATTENING → CLOSED`. The flatten step is a
top-level task independent of the strategy — it runs even if the strategy loop
is stuck, and it re-verifies flatness via REST before declaring `CLOSED`.

Dead-man's switch analog: Tradovate `cancelAllOrders` on SIGINT/SIGTERM +
`flatten_on_disconnect` — if the order WS drops and cannot reconnect within
its backoff budget while holding a position, the bot liquidates via REST.

---

## 8. Trade Decision Pipeline

The kraken two-layer signal engine gains three futures gates **in front**:

```
Book/DOM update received
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│ Gate F1: Session      outside 08:00→16:00 ET?  ──► SKIP  │
│ Gate F2: News         inside a blackout window? ──► SKIP │
│ Gate F3: Contract     active_contracts stale?   ──► SKIP │
├──────────────────────────────────────────────────────────┤
│ Gate 0:  Pre-checks   spread > max_spread_ticks, order   │
│                       cooldown, NACK pause      ──► SKIP │
├──────────────────────────────────────────────────────────┤
│ Layer 1: Order Flow   score = 0.6·imbalance +            │
│                       0.4·trade_delta; confidence gate   │
├──────────────────────────────────────────────────────────┤
│ Layer 2: Price Action EMA trend / V-exhaustion / re-test │
│                       (same truth table as kraken bot)   │
└────────────────────────────┬─────────────────────────────┘
                             │ PASS
                      ┌──────┴──────┐
                    BUY            SELL
                      │              │
              pos < max_contracts   pos > −max_contracts
                      │              │
               limit @ best bid  limit @ best ask
               (tick-quantized, on the ACTIVE contract month)
```

Unlike the spot bot, SELL with no position opens a **short** — futures are
symmetric. `max_contracts` bounds absolute net position in both directions.

---

## 9. Directory Structure

```
tradovate/
│
├── launcher.py                # spawns processes for products with trade: true
├── main.py                    # single-product entrypoint: main.py --product MES
├── reference_daemon.py        # daily calendar + volume/OI jobs (one instance)
├── pyproject.toml
│
├── config/
│   ├── config.yaml            # mode switches, session, news guard, resolver,
│   │                          # strategy & risk defaults        [EXISTS]
│   └── products.yaml          # full mini/micro catalog + trade flags [EXISTS]
│
├── docs/
│   └── README.md              # this document                   [EXISTS]
│
├── src/                       # (see Component Map, §4)
│
├── data/
│   └── tradovate_bot.db       # SQLite (auto-created)
│
├── monitoring/                # prometheus.yml + grafana dashboards
└── logs/                      # one rotating log per product
```

---

## 10. Database Schema

```sql
-- who is the live contract for each product
CREATE TABLE active_contracts (
  product        TEXT PRIMARY KEY,   -- 'MES'
  contract_code  TEXT NOT NULL,      -- 'MESU6'
  contract_month TEXT NOT NULL,      -- 'SEP 2026'
  trade_date     TEXT NOT NULL,      -- CME data date (YYYY-MM-DD)
  volume         INTEGER,
  open_interest  INTEGER,
  roll_pending   INTEGER DEFAULT 0,
  updated_at     TEXT NOT NULL
);

CREATE TABLE volume_oi_history (
  product TEXT, contract_code TEXT, trade_date TEXT,
  volume INTEGER, open_interest INTEGER,
  PRIMARY KEY (product, contract_code, trade_date)
);

CREATE TABLE news_events (
  event_time_utc TEXT, title TEXT, currency TEXT, impact TEXT,
  scraped_at TEXT,
  PRIMARY KEY (event_time_utc, title)
);

CREATE TABLE fills (
  id INTEGER PRIMARY KEY, product TEXT, contract_code TEXT,
  side TEXT, qty INTEGER, price REAL, fee REAL, ts TEXT
);

CREATE TABLE equity_snapshots (
  ts TEXT PRIMARY KEY, realized_pnl REAL, unrealized_pnl REAL, open_positions TEXT
);
```

SQLite runs in WAL mode: the reference daemon is the only writer to reference
tables; product processes write only their own `fills` rows.

---

## 11. Configuration Reference

See [`config/config.yaml`](../config/config.yaml) (inline-documented). Summary:

| Block | Key settings |
|-------|--------------|
| `mode` | `dry_run`, `live_trading` — the two account-level switches (§2) |
| `tradovate` | demo/live REST + WS URLs; credentials via env vars only |
| `session` | `open: 08:00`, `close: 16:00` ET, `flatten_buffer_minutes: 5`, Sun–Fri |
| `news_guard` | USD + high impact, 15 min before/after, daily 18:00 ET refresh, `position_policy` |
| `contract_resolver` | daily 18:30 ET, `max_volume_and_oi` rule, 48 h staleness guard |
| `shared_services` | structure engine, levels service, regime classifier, trailing-exit engine, execution guards |
| `strategies` | 23 playbook modules with skill number, tier, priority, and `enabled` flags |
| `risk_operations` | operational switches only (`flatten_on_disconnect`, one strategy per product) |

**Risk is configured per product, not globally**: every product entry in
`products.yaml` carries a required `risk:` block (`max_contracts`,
`risk_per_trade_pct`, `stop_loss_usd`, `risk_reward_ratio`,
`partial_exit_ladder`, `breakeven_after_t1`, `trail_step_pct`,
`daily_loss_limit_usd`) so clients control risk values product by product.
A product with no risk block fails config validation at startup — there is no
generic fallback to inherit. Strategy parameter overrides (any
`strategies.<module>.params` key) nest under `overrides:` on the product entry.

---

## 12. Risk Management

All risk-appetite values come from the product's own `risk:` block in
`products.yaml` (§11). The trailing-stop engine, ported and converted to ticks:

```
stop_ticks = ceil(stop_loss_usd / (tick_value × max_contracts))
tp_ticks   = stop_ticks × risk_reward_ratio
trail_step = tp_ticks × trail_step_pct        (in ticks, floor 1)

Example — MES (tick_value $1.25), stop_loss_usd $50, 1 contract:
  stop_ticks = 40 ticks (10.00 index pts)   tp_ticks = 120 ticks (30.00 pts)
  Milestone 1: SL → break-even    Milestone N: SL += trail_step
  SL only advances — never retreats.
```

Additional futures-specific layers:
- **Daily loss limit** — realized session P&L ≤ −`daily_loss_limit_usd` stops
  new entries until the next session open.
- **Session flatten** — hard-flat by 16:00 ET daily (§7); no overnight-into-
  maintenance exposure, no weekend exposure.
- **News blackouts** — §6.
- **Margin awareness (roadmap)** — check Tradovate `cashBalance`/margin before
  entry; skip if initial margin of the new contract exceeds free cash.

---

## 13. Monitoring

Same Prometheus + Grafana stack as the kraken bot (ports 8100+N per product),
plus futures-specific series:

| New metric | Type | Meaning |
|------------|------|---------|
| `bot_active_contract_info` | Gauge (labels) | current contract code per product |
| `bot_session_state` | Gauge | 0=CLOSED, 1=OPEN, 2=FLATTENING |
| `bot_news_blackout` | Gauge | 1 while inside a blackout window |
| `bot_next_news_seconds` | Gauge | seconds until next red-folder event |
| `bot_roll_pending` | Gauge | 1 when resolver flagged a roll |
| `bot_daily_realized_pnl_usd` | Gauge | resets at session open |

---

## 14. Build Roadmap

| Phase | Deliverable | Depends on |
|-------|-------------|-----------|
| 1 | `storage/db.py` + schema, `config` loaders (this design's contracts) | — |
| 2 | `reference/volume_oi.py` + `contract_resolver.py` (+ CLI: `python -m reference.resolver --once`) | 1 |
| 3 | `reference/ff_calendar.py` + `reference_daemon.py` (APScheduler) | 1 |
| 4 | `auth/` + `client/` — Tradovate token, REST, WS frame protocol, DOM subscribe on demo | — |
| 5 | `scheduling/session_manager.py` + `news_guard.py` with unit tests (freeze-time) | 1,3 |
| 6 | Port `trading/` engine from kraken (tick-quantized), `main.py` wired end-to-end in `dry_run` | 2,4,5 |
| 7 | `launcher.py` multi-product + monitoring stack | 6 |
| 8 | Demo-account soak (dry_run=false, live_trading=false) on MES/MNQ, then live checklist | 7 |

### Pre-Live Checklist

- [ ] `dry_run: false` and `live_trading: true` set intentionally; launcher run with `--confirm-live`
- [ ] Only intended products have `trade: true`
- [ ] `active_contracts` fresh (< 24 h) for every enabled product
- [ ] Today's news events present in `news_events` (check count > 0 on CPI/NFP days)
- [ ] Observed one full 15:55 ET flatten on the demo account
- [ ] `stop_loss_usd` × products ≤ capital you accept losing in one session
- [ ] Tradovate API access is on a dedicated sub-account with only trading permissions

---

*Python 3.11+ · Tradovate REST/WS API · CME Globex · SQLite + APScheduler · Prometheus + Grafana*
