# Tradovate CME Futures AI Trading Bot — Architecture

A multi-product, fully-async **futures** trading bot for CME Globex markets, executed
through the [Tradovate](https://tradovate.com) API, organized as two planes:

- an **execution plane** — ports the order-flow / EMA-trend / V-exhaustion engine
  from the sibling `kraken_ai_trading` bot and adds the three subsystems futures
  require that spot crypto does not: active-contract resolution (daily CME
  Volume & Open Interest), an economic-news guard (ForexFactory red-folder
  blackouts), and session management (08:00–16:00 ET day session, flatten at close);
- a **research plane** — a gated strategy-validation factory following the
  methodology in Kevin Davey's *Building Winning Algorithmic Trading Systems*
  (Wiley, 2014 — `docs/Algorithmic trading system.pdf`): every strategy must earn
  live capital through limited testing → walk-forward → Monte Carlo → incubation,
  position sizing is fixed-fractional and Monte Carlo-calibrated, and live
  strategies are tracked against their statistical expectation bands with a
  pre-committed quitting point.

The core insight adopted from the book: *the execution engine is not the edge — the
validation pipeline is.* Davey reports needing 100–200 tested ideas to find one
worth trading. The 23 playbook strategy modules in `config.yaml` are therefore
**candidates in a strategy factory**, most of which are expected to be discarded.

---

## Table of Contents

**System**
1. [Architecture Overview](#1-architecture-overview)
2. [The Safety Model](#2-the-safety-model)
3. [Product Universe](#3-product-universe)

**Execution plane**
4. [Active-Contract Resolver](#4-active-contract-resolver)
5. [News Guard](#5-news-guard)
6. [Session Manager](#6-session-manager)
7. [Trade Decision Pipeline](#7-trade-decision-pipeline)

**Research plane**
8. [The Strategy Lifecycle — Gates G0→G6](#8-the-strategy-lifecycle--gates-g0g6)
9. [Backtest Engine](#9-backtest-engine)
10. [Walk-Forward Analysis](#10-walk-forward-analysis)
11. [Monte Carlo Analysis](#11-monte-carlo-analysis)
12. [Incubation](#12-incubation)
13. [Risk, Position Sizing & Money Management](#13-risk-position-sizing--money-management)
14. [Diversification Controls](#14-diversification-controls)

**Operations**
15. [Monitoring: Infrastructure & Expectation](#15-monitoring-infrastructure--expectation)
16. [Reconciliation & Fill-Integrity Audit](#16-reconciliation--fill-integrity-audit)
17. [Tradovate API Constraints & Compliance](#17-tradovate-api-constraints--compliance)

**Reference**
18. [Component Map](#18-component-map)
19. [Directory Structure](#19-directory-structure)
20. [Database Schema](#20-database-schema)
21. [Configuration Reference](#21-configuration-reference)
22. [Build Roadmap](#22-build-roadmap)
23. [Pre-Live Checklist](#23-pre-live-checklist)

---

## 1. Architecture Overview

```
┌─────────────────────────────── RESEARCH PLANE ─────────────────────────────┐
│                                                                            │
│  historical bars ──► backtester ──► walk-forward ──► Monte Carlo ──► gate  │
│  (data_store)        (pessimistic    harness          simulator      keeper │
│                       fill model)    (in/out folds)   (2,500 runs)          │
│                                                                            │
│  Writes: backtest_runs · walkforward_folds · monte_carlo_runs ·            │
│          strategy_lifecycle (the ONLY authority for what may go live)      │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   │ lifecycle_state per (strategy, product)
                                   ▼
┌────────────────────────────── EXECUTION PLANE ─────────────────────────────┐
│                            launcher.py                                     │
│                  (spawns one process per product with                      │
│                       trade: true in products.yaml)                        │
│                                                                            │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                  │
│   │ MES Process  │   │ MNQ Process  │   │ MCL Process  │   ...            │
│   │ main.py MES  │   │ main.py MNQ  │   │ main.py MCL  │                  │
│   │ port :8101   │   │ port :8102   │   │ port :8103   │                  │
│   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘                  │
│          └──────────────────┼──────────────────┘                          │
│                             │ reads                                       │
│   ┌─────────────────────────▼──────────────────────────┐                 │
│   │              SQLite  data/tradovate_bot.db          │                 │
│   │  active_contracts │ news_events │ fills │ vol_oi    │                 │
│   │  strategy_lifecycle │ monte_carlo_runs │ …          │                 │
│   └─────────────────────────▲──────────────────────────┘                 │
│                             │ writes (daily jobs)                         │
│   ┌─────────────────────────┴──────────────────────────┐                 │
│   │            reference_daemon.py (scheduler)          │                 │
│   │  18:00 ET  ForexFactory calendar scrape (USD, red)  │                 │
│   │  18:30 ET  CME Volume & OI pull → active contracts  │                 │
│   └────────────────────────────────────────────────────┘                 │
│                                                                           │
│   reconciler ─► statements vs fills · orphan orders · flat checks         │
│   monitor    ─► live equity vs Monte Carlo expectation bands              │
│                                                                           │
│   ┌────────────── broker gateway — the ONE Tradovate session ─────────┐   │
│   │  one auth token · one trading WS · one market-data WS · REST      │   │
│   │  product processes attach via local RPC (Tradovate allows a       │   │
│   │  single API connection per user — attestation #19)                │   │
│   │  rate-limit budgeter: 429 backoff + time-penalty ticket replay    │   │
│   │  stamps isAutomated: true on every order (attestation #7)         │   │
│   └───────────────────────────────┬───────────────────────────────────┘   │
└───────────────────────────────────┼───────────────────────────────────────┘
                                    │                          │
                                    ▼                          ▼
┌─────────────────────────┐  ┌──────────────────────────────────────────┐
│  Tradovate REST + WS    │  │  Reference sources (HTTP, daily)          │
│  auth: accessTokenRequest│ │  cmegroup.com/markets/<slug>/volume       │
│  orders: placeOrder,    │  │  forexfactory.com/calendar                │
│    cancelOrder, liquidate│ └──────────────────────────────────────────┘
│  md: wss://md.tradovate…│
│  demo vs live URL picked │
│  by mode switches        │
└─────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Process-per-product isolation** | Same as kraken bot: one crash never kills the fleet; tune/restart one product independently |
| **Shared reference daemon** | Volume/OI and the news calendar are account-wide facts — scraped once, stored in SQLite, read by every product process. Avoids 30 processes hammering CME/ForexFactory |
| **SQLite as the contract of record** | Product processes never scrape; they only read `active_contracts` and `news_events`. If reference data is stale (> 48 h) the process refuses to trade |
| **Three-switch safety model + lifecycle gate** | `dry_run`, `live_trading`, per-product `trade` — see §2. Live orders require two deliberate flips plus a product opt-in, and behind all of that a strategy must be `live` in `strategy_lifecycle` |
| **Tick-native math** | All prices quantized to `tick_size`; all risk converted USD → ticks via `tick_value`. No floating-point price drift on order placement |
| **Flatten-at-close is unconditional** | The 15:55 ET flatten runs even if strategy/news modules are wedged — it is a top-level watchdog, not a strategy behavior |
| **Lifecycle gate, not an `enabled` flag** | An `enabled: true` edit must not be able to put an unvalidated strategy on live capital. The gate keeper enforces state transitions; config can only *request* them |
| **Pessimistic fill model everywhere** | Davey's rule: assume a limit order fills only if price *penetrates* it (touch-fills happen only ~5–20% of the time live). Backtests that buy the low / sell the high of bars are rejected automatically. Live results should then only beat the backtest |
| **Incubation is a first-class runtime mode** | 3–6 months of paper-tracking on unseen live data before capital, evaluated monthly like an extra out-of-sample period. Catches development mistakes (overfit, hindsight bias) that no backtest can |
| **Sizing derived from Monte Carlo, capped by config** | Fixed-fractional `N = int(x · Equity / LargestLoss)` with `x` chosen from Monte Carlo sweeps subject to max-drawdown and risk-of-ruin ceilings — never from a single historical equity curve |
| **Every live strategy has a pre-committed quitting point** | Decided *before* going live from the Monte Carlo drawdown distribution. Hitting it retires the strategy regardless of any narrative. Prevents "doubling down" on a broken system |
| **Daily reconciliation is mandatory** | Davey's live-trading incident: an order that should have auto-cancelled rested overnight and filled into a rogue position, discovered 30+ hours late. The reconciler exists to find that class of failure within minutes, not days |
| **Single-session broker gateway** | Tradovate permits **one API connection per user** (attestation #19 — even a Tradovate Trader login kills the bot's session). Product processes therefore never talk to the broker directly; one gateway process owns the token, both websockets, and the request budget |
| **Server-side OSO stop brackets** | Entries are submitted as OSO with the protective stop attached at the exchange. A crashed process still leaves a working stop; the local trailing engine *modifies* the resting stop instead of holding it in memory |
| **Rate-limit budget is a first-class resource** | All REST/WS traffic draws from the gateway's budgeter (429 backoff, time-penalty ticket replay — attestations #21–26). Order actions have absolute priority; reconciler polling and MD subscriptions use what's left |

---

## 2. The Safety Model

Three switches live in config (`config/config.yaml` + `config/products.yaml`):

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

**Fifth gate (lifecycle):** even with all four switches set, the order router
refuses to trade any strategy module whose `strategy_lifecycle` state is not
`live` (§8). Config can request; only the gate keeper promotes.

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

## 4. Active-Contract Resolver

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

## 5. News Guard

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

## 6. Session Manager

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

The session manager also refuses to leave `CLOSED` while the reconciler's
`bot_reconciliation_ok` gauge is 0 (§16).

---

## 7. Trade Decision Pipeline

The kraken two-layer signal engine gains three futures gates **in front**:

```
Book/DOM update received
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│ Gate F1: Session      outside 08:00→16:00 ET?  ──► SKIP  │
│ Gate F2: News         inside a blackout window? ──► SKIP │
│ Gate F3: Contract     active_contracts stale?   ──► SKIP │
│ Gate F4: Lifecycle    module not live/incubating?──► SKIP│
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
Incubating modules (§12) pass gate F4 but route to the paper-fill engine, never
to the broker.

Entries are submitted as **OSO brackets**: the initial protective stop rides
server-side at the exchange from the moment of fill, and the trailing engine
(§13) thereafter *modifies* the resting stop rather than holding it locally.
Every order carries `isAutomated: true` (§17).

### Strategy arbitration — which module owns a product

`max_concurrent_strategies_per_product: 1` (§14) says only **one** module may
be live on a product; the **strategy router**
(`shared_services.strategy_router` in `config.yaml`) says *which* one when
several qualify. Those are two different rules — "only one runs" versus "which
one wins the tie" — and the tie-breaker is explicit config so it never
resolves by accident. Selection runs top-to-bottom, each rule narrowing the
field:

1. **Eligibility** — `enabled: true`, `lifecycle_state` is `live` (or
   `incubation`, which routes to paper fills), and gates F1–F4 pass.
2. **Regime specificity** — the module whose declared regime gate most tightly
   matches the classifier's current state wins: a strong clean trend selects
   the pure trend-follower, a rotational day selects the fade module. The
   router selects **before entries are considered** — only the winner is even
   allowed to look for a signal, so "two strategies want to enter at the same
   instant" cannot arise by construction.
3. **Priority** — the playbook build tier breaks regime ties (1 beats 2
   beats 3).
4. **Config order** — final deterministic tie-break: first declared under
   `strategies:` wins. The selection is therefore a pure function of config
   plus regime state — reproducible bar-for-bar in the backtester (§9), which
   replays the same router.

The router re-evaluates on regime change or session open — **never
mid-position**: an open position is always managed to completion by the module
that opened it (`handoff: flat_only`); the router may switch modules only when
the product is flat.

---

## 8. The Strategy Lifecycle — Gates G0→G6

Every `(strategy_module, product)` pair moves through this state machine, persisted
in the `strategy_lifecycle` table. Transitions forward require passing the gate;
any failed gate sends the pair to `retired` (with the failure recorded — the
factory's discard pile is data too).

```
 idea ──G1──► limited_test ──G2──► walk_forward ──G3──► monte_carlo
                                                            │G4
 retired ◄──(any gate failed / quitting point hit)          ▼
    ▲                                                  incubation
    │G6 (quit)                                              │G5
    └───────────────────────── live ◄───────────────────────┘
```

| Gate | Question it answers | Pass criteria (defaults, per `research:` config) |
|------|--------------------|--------------------------------------------------|
| **G1 → limited_test** | Is the idea worth computer time? | A complete **playbook card** (`config/playbook/<module>.yaml`): written goal/objective, fully mechanical entry & exit (no discretionary or repainting inputs), and an empty `ambiguities_open` list — the playbook's priority-3 ambiguities must be resolved on the card before any computer time is spent |
| **G2 → walk_forward** | Does a quick, cheap test show an edge? | Limited backtest (recent 1–2 y, 1 contract, pessimistic fills, costs included) shows positive expectancy; no red-flag artifacts (§9) |
| **G3 → monte_carlo** | Does the edge survive out-of-sample? | Walk-forward efficiency ≥ 50% (out-of-sample profit rate vs in-sample); combined out-of-sample equity meets the strategy's stated goal; in/out periods chosen on holdout data, not optimized (§10) |
| **G4 → incubation** | What are the realistic risk odds? | Monte Carlo (2,500 iterations) annual **return / max drawdown ≥ 2.0**; risk of ruin ≤ 10%; median max drawdown within the product's tolerance (§11) |
| **G5 → live** | Did it work on data nobody touched? | 3–6 months incubation; paper equity within the Monte Carlo expectation cone (above the lower-10% band at review); no unresolved fill-model discrepancies (§12) |
| **G6 (ongoing)** | Should it keep trading? | Live equity above quitting point; monthly review answers "no reason to stop" (§15). Semi-annual *next-best-alternative* review may also replace it |

Rules enforced by the **gate keeper** (`research/gatekeeper.py`):

- **G1 requires the playbook card.** Each module has one YAML card in
  `config/playbook/` (schema in that directory's README) holding the goal,
  the mechanical rule statements, and its ambiguity ledger. The gatekeeper
  blocks `idea → limited_test` while the card is missing or `ambiguities_open`
  is non-empty, and records the card's git commit hash as the G1 evidence on
  the lifecycle row. Cards carry a `status_requested` field only — actual
  state lives exclusively in the DB, so no card or config edit can promote a
  strategy.
- The execution plane refuses to route live orders for any module whose
  `lifecycle_state != live` — regardless of `enabled:` in config. `incubation`
  modules run in per-strategy paper mode even inside a live process.
- Re-testing after a failed gate with loosened criteria is the classic
  self-deception the book warns about ("the more you touch the data, the more
  likely you are to fit the system to it"). A retired pair can only re-enter at
  `idea` as a *new* row, keeping the full audit trail of prior failures.
- One live experiment at a time per product (`max_concurrent_strategies_per_product: 1`
  already enforces this at runtime; the lifecycle table enforces it at promotion time).

---

## 9. Backtest Engine

Package `src/research/`. The backtester replays historical bars/DOM through the
*same* strategy modules and shared services the live process uses (one code path —
a strategy that only exists in a vectorized research notebook is a different
strategy).

**Pessimistic fill model** (non-configurable floor, per the book's backtest-honesty
rules):

- Limit orders fill only when price trades **through** the limit, not on touch.
- No buy fills at the exact low of a bar, no sell fills at the exact high — runs
  showing >2% of such fills are flagged and the run is rejected.
- No same-bar entry+exit; stops/targets tighter than the bar resolution force a
  finer data resolution or a rejection.
- No synthetic bar types (Renko etc.) — already excluded by the playbook (skill 18).
- Slippage (`execution_guards.slippage_model_ticks`) and commissions applied to
  every fill; the reconciler later verifies live slippage against this model (§16).

**Data store**: continuous per-product history stitched from individual contract
months using the roll dates the resolver already records in `volume_oi_history` —
backtests roll exactly when the live bot would have rolled.

---

## 10. Walk-Forward Analysis

`research/walkforward.py` — in-depth testing per the book's Chapter 13:

```
history: [ in-sample (optimize) ][ out ][ in ][ out ] ...   → stitched
                                                              out-of-sample-only
                                                              equity curve
```

- Optimize parameters on each in-sample window; trade them unchanged on the next
  out-of-sample window; roll forward. Only the stitched **out-of-sample** curve is
  judged.
- **In/out period selection is itself an optimization.** Per the book's "walk-forward
  inside a walk-forward": choose the best in/out combination on the *older* portion
  of history, then confirm it once on a final untouched holdout (most recent ~3
  years). If the holdout fails, the strategy is abandoned — not re-tuned.
- Fitness function caution: metrics like max drawdown and return-on-account are
  **not additive** across windows; the harness always recomputes them on the
  stitched curve rather than summing per-window values.
- Output includes the **walk-forward history parameter set** (parameters as a
  function of date), so incubation and live replay use exactly the parameters the
  analysis chose — and the largest single walk-forward loss, which feeds position
  sizing (§13).

---

## 11. Monte Carlo Analysis

`research/montecarlo.py` — the trade list from the walk-forward out-of-sample curve
is resampled (order-randomized) for **2,500 iterations** per scenario, producing
distributions rather than a single historical path:

| Output | Used for |
|--------|----------|
| Annual return / max drawdown ratio | **Gate G4: must be ≥ 2.0** (below that, the risk isn't paying) |
| Median & 95th-percentile max drawdown | Product risk-block sanity + quitting point (§15) |
| Risk of ruin (equity ≤ quitting-point capital) | Gate G4: ≤ 10% |
| Probability of profit in one year | Diversification comparisons (§14) |
| Expectation cone (average / top-10% / lower-10% equity paths) | Incubation & live tracking bands (§12, §15) |
| Return/DD as a function of fixed fraction `x` | Position-sizing calibration (§13) |

All runs are persisted (`monte_carlo_runs`) — the bands drawn on live dashboards
must be reproducible from a stored run ID, not recomputed ad hoc.

---

## 12. Incubation

The step the book calls the hardest psychologically: after Monte Carlo passes, the
strategy **waits 3–6 months** trading paper-only on live data before touching
capital.

Implementation — a per-strategy mode inside the normal product process (not a
separate deployment):

- The module receives live ticks, generates signals, and "fills" them through the
  same pessimistic fill model as the backtester; results go to `incubation_equity`.
- Runs alongside whatever module is live on that product — incubation consumes no
  position limits and places no orders.
- **Monthly review** (scheduled job, results to the dashboard): is paper equity
  inside the Monte Carlo cone? Above the lower-10% band? Do paper fills match what
  the Tradovate demo account produces for the same signals? (For limit-entry
  strategies, a short demo-account leg may be added specifically to validate the
  fill model — the one case the book flags where simulation alone can mislead.)
- Early promotion is not supported. There is deliberately no config override to
  shorten incubation below `research.incubation_min_days` — that pressure valve is
  exactly what incubation exists to resist.

---

## 13. Risk, Position Sizing & Money Management

**Risk is configured per product, not globally**: every product entry in
`products.yaml` carries a required `risk:` block (`max_contracts`,
`risk_per_trade_pct`, `stop_loss_usd`, `risk_reward_ratio`, `trail_step_pct`,
`daily_loss_limit_usd`) so clients control risk values product by product.
A product with no risk block fails config validation at startup — there is no
generic fallback to inherit.

### Trailing-stop engine (ported from kraken, converted to ticks)

```
stop_ticks = ceil(stop_loss_usd / (tick_value × max_contracts))
tp_ticks   = stop_ticks × risk_reward_ratio
trail_step = tp_ticks × trail_step_pct        (in ticks, floor 1)
```

The trail is **discrete (quadrant-stepped), not continuous** — and
`trail_step_pct` is a fraction of the **entry→target distance**, not of the
entry price. With `trail_step_pct: 0.25` the entry→TP journey splits into four
quadrants of `trail_step` ticks each; the stop sits still inside a quadrant and
jumps only when price completes one:

- Milestone `k` fires when price reaches `entry + k × trail_step` (long; mirrored
  for shorts). The stop then moves to `entry + (k−1) × trail_step` — one
  quadrant behind price. `k = 1` is break-even.
- Each R-level is converted to a price and rounded to the product's `tick_size`.
- The stop only ever ratchets toward profit — never retreats, never moves before
  price has earned the level. Milestone `N` (= `1 / trail_step_pct`) is the TP:
  full exit.

Example — YM (tick_value $5, tick 1 pt), `stop_loss_usd` $500,
`risk_reward_ratio` 3, 1 contract, entry 40,000 long
(stop = 100 pts = 1R, TP = 300 pts, trail_step = 75 pts):

| Price reaches      | Quadrant done | Stop moves to        | Locked        |
|--------------------|---------------|----------------------|---------------|
| 40,000 (entry)     | —             | 39,900 (−1R)         | −$500 at risk |
| 40,075 (+0.75R)    | Q1            | 40,000 (break-even)  | $0            |
| 40,150 (+1.5R)     | Q2            | 40,075 (+0.75R)      | +$375         |
| 40,225 (+2.25R)    | Q3            | 40,150 (+1.5R)       | +$750         |
| 40,300 (+3R = TP)  | Q4            | — full exit          | +$1,500       |

Partial exits are a **strategy** concern, not a product-risk one — the risk
block deliberately carries no partial-exit ladder. Strategies that scale out
(e.g. `two_legged_pullback`'s t1/t2 bracket) define those targets in their own
`params` block in `config.yaml`, gated by `min_contracts_for_partials`; with
1 contract the quadrant trail to the `risk_reward_ratio` target governs the
whole position. When strategy partials and the trail coexist, the live stop is
always the **maximum** (most profit-protective) of every mechanism's level —
the stop still only ratchets up.

Implementation-wise the quadrant trail is a **provider of the shared
`trailing_exit_engine`** (`shared_services` in `config.yaml`), selected the
same way strategies are: every provider carries an `enabled` flag, and
**exactly one may be `enabled: true`** — that one is the engine default
(`quadrant` today). Zero or two-plus enabled providers fail config validation
at startup, the same no-silent-fallback rule as the per-product risk block.
The quadrant provider takes no parameters of its own — its geometry is derived
per product from the risk block (`risk_reward_ratio` × `trail_step_pct`).
Strategies whose edge is defined by a structural exit may name an indicator
provider in their own params (`supertrend | sma20 | donchian_mid | fractal |
sar`); that override applies only while the strategy is the live module on the
product, and since `max_concurrent_strategies_per_product` is 1, **each
product has exactly one trail provider in use at any moment**. Whichever
provider is active, the product risk block's hard caps and the ratchet-only
stop invariant still apply.

### Position sizing (fixed-fractional, Monte Carlo-calibrated)

Static `max_contracts` remains the hard cap; the sizing engine within it is the
book's **fixed-fractional** model:

```
N = int( x · Equity / LargestLoss )          # always round down
N = min(N, risk.max_contracts)               # config cap still absolute
N = max(N, 1) while equity ≥ minimum         # start small, scale with profits

Equity      = current account equity (Tradovate cashBalance, snapshot at entry)
LargestLoss = largest single-trade loss from walk-forward out-of-sample history
x           = fixed fraction — calibrated per strategy, NOT hand-picked
```

Calibration of `x` (per strategy, per the book's Chapter 16):

1. Sweep `x` through the Monte Carlo simulator.
2. Discard every `x` violating the constraints in the product's risk block:
   median max drawdown ≤ `sizing.max_drawdown_pct`, risk of ruin ≤
   `sizing.max_risk_of_ruin_pct`.
3. Of the survivors, pick the `x` maximizing return/drawdown. (The unconstrained
   peak — Vince's optimal-f region — is explicitly *not* used: in the book's own
   example it implied a coin-flip chance of a ~67% drawdown.)
4. For **multiple concurrent live strategies**, `x` values are re-optimized
   *jointly* on the combined Monte Carlo (correlated strategies must share the risk
   budget — per-strategy `x` values are not independent).

Principles encoded as invariants:

- New live strategies always start at **1 contract** regardless of formula output
  (`sizing.warmup_trades` before formula sizing activates).
- Sizing never rescues a losing strategy and can destroy a winning one — hence the
  constraint-first calibration and the absolute config cap.
- Martingale/no-limit progressions are structurally impossible: `N` is a pure
  function of equity, never of recent losses (playbook skill-5 verdict upheld).

### Additional futures-specific layers

- **Daily loss limit** — realized session P&L ≤ −`daily_loss_limit_usd` stops
  new entries until the next session open; a portfolio-level
  `portfolio_daily_loss_limit_usd` above it flattens and halts *all* products (§14).
- **Session flatten** — hard-flat by 16:00 ET daily (§6); no overnight-into-
  maintenance exposure, no weekend exposure.
- **News blackouts** — §5.
- **Margin monitor** — before every entry, compare Tradovate `cashBalance`
  against the initial margin of the new contract plus a safety buffer, and skip
  the entry if it doesn't fit. The API returns raw data only — net-liq, P&L, and
  margin math are the bot's own responsibility (§17). Tradovate auto-liquidates
  accounts that fall below the greater of $500 or 3% of initial margin, at the
  holder's expense, so the bot's limits must trip long before the broker's do;
  the 15:55 ET flatten also keeps the account clear of the 4:45 PM ET margin
  deadline.

---

## 14. Diversification Controls

The book's four diversification measurements become a scheduled portfolio report
(`research/diversification.py`, weekly):

1. **Daily-return correlation matrix** across all live + incubating strategies
   (full history and rolling 6-month windows — long-run low correlation does not
   preclude crisis correlation, so both are shown).
2. **Equity-curve linearity** — R² of a linear regression on each equity curve and
   on the combined curve; combined R² should beat the components.
3. **Combined max drawdown** vs the components'.
4. **Combined Monte Carlo return/DD and probability of profit** vs each component —
   the decisive metric when the drawdown comparison is ambiguous.

Consequences in config/runtime:

- A candidate strategy that is highly correlated with an already-live one
  (`corr > research.max_new_strategy_correlation`) is held at G5 even if its solo
  numbers pass — it adds size, not diversification.
- Near-substitute pairs the playbook already identified
  (`donchian_pullback` ↔ `supertrend_rsi`, `vwap_band_fade` ↔ `vwap_rsi_pullback`)
  may only have one member live per product.
- Portfolio-level `daily_loss_limit_usd` (in `risk_operations`) sits above the
  per-product limits: breaching it flattens and halts *all* products for the day.

---

## 15. Monitoring: Infrastructure & Expectation

### Infrastructure metrics

Same Prometheus + Grafana stack as the kraken bot (ports 8100+N per product),
plus futures-specific series:

| Metric | Type | Meaning |
|--------|------|---------|
| `bot_active_contract_info` | Gauge (labels) | current contract code per product |
| `bot_session_state` | Gauge | 0=CLOSED, 1=OPEN, 2=FLATTENING |
| `bot_news_blackout` | Gauge | 1 while inside a blackout window |
| `bot_next_news_seconds` | Gauge | seconds until next red-folder event |
| `bot_roll_pending` | Gauge | 1 when resolver flagged a roll |
| `bot_daily_realized_pnl_usd` | Gauge | resets at session open |
| `bot_orphan_orders_total` | Counter | orders at broker the bot didn't know about (§16) |
| `bot_position_mismatch` | Gauge | 1 while broker vs internal position disagree |
| `bot_slippage_ticks_actual` | Histogram | live slippage vs model |
| `bot_reconciliation_ok` | Gauge | per product; session won't open while 0 |

### Statistical monitoring — is the live strategy still the one we validated?

**The two standing charts** (Grafana, fed from `live_vs_expected`):

1. **Big-picture equity overlay** — walk-forward, incubation, and live segments on
   one curve. Healthy = the three segments share roughly the same slope; a live
   slope that visibly breaks from the historical one is the earliest failure signal.
2. **Expectation cone** — cumulative live P&L plotted against the stored Monte
   Carlo average / top-10% / lower-10% paths from the promoting run. Sustained
   tracking at or below the lower-10% band means live behavior is close to being
   a *different system* than the one validated — reviewed monthly, not intraday.

**Weekly automated review** — the book's recurring question set, rendered as a
checklist with data attached, answered by the operator (not auto-actioned):

- Are results in line with expectations (which band are we in)?
- Are live fills comparable to the fill model (slippage delta from §16)?
- Any reason to stop trading this system?
- Any reason to change the position-sizing plan (reduce or increase risk)?

**Quitting point** (auto-enforced, the one check that *is* actioned): fixed before
go-live from the Monte Carlo drawdown distribution (default: 95th-percentile max
drawdown × `research.quit_multiplier`). If live drawdown breaches it, the gate
keeper retires the strategy and the process stops routing its orders at the next
session open. No same-day re-enable exists.

**Semi-annual next-best-alternative review**: every ~6 months, compare each live
strategy against the bench (incubated strategies awaiting capital). A live
strategy can be replaced by a better alternative even while profitable — but no
strategy is benched in its first 6 months (systems need time to show long-term
expectancy), and the quitting point always overrides.

---

## 16. Reconciliation & Fill-Integrity Audit

Module `src/audit/reconciler.py`, born directly from the book's week-9 live
incident (a should-have-been-cancelled limit order filled overnight into an
unnoticed position). "Automated trading does not mean unattended trading" —
so the attendance is itself automated:

| Check | Cadence | Action on mismatch |
|-------|---------|--------------------|
| Working orders at broker vs orders the bot believes exist | Every 5 min while OPEN | Cancel orphans immediately; page operator |
| Broker positions vs internal `position.py` state | Every 5 min while OPEN; once after flatten | If flatten-verified but broker shows a position → liquidate + page |
| Broker fills vs `fills` table | Hourly + end of session | Missing/extra fills logged, P&L recomputed from broker as truth |
| Live slippage vs `slippage_model_ticks` | Per fill, aggregated daily | Rolling actual-vs-modeled slippage metric; sustained excess → review fill model |
| End-of-day statement reconciliation | Daily 17:00 ET | Daily P&L report; any unexplained delta blocks the next session's open until acknowledged |

All reconciler polling flows through the gateway's rate budget (§17), with order
actions taking absolute priority — the audit may slow down under load, but it can
never starve order traffic.

---

## 17. Tradovate API Constraints & Compliance

Constraints from Tradovate's 32-point partner-API self-attestation
(`docs/tradovate-api-32-point-attestation-checklist.md`) that materially shape
the design, and how the architecture answers each:

| # | Constraint | Design response |
|---|-----------|-----------------|
| 7 | Automated orders must be flagged `isAutomated` | `orders.py` stamps `isAutomated: true` on every order — hard-coded, not configurable |
| 16 | Market/Limit/Stop/Stop-Limit/Trailing/OCO/OSO order types | Entries go out as **OSO brackets** (entry + server-side stop); trailing is implemented by modifying the resting stop (§7, §13) |
| 17 | API returns raw data only — P/L, net-liq, margin must be self-computed | `position.py` computes open/realized P&L; the margin monitor computes requirements pre-entry (§13) |
| 18 | Device ID required for authentication (2FA) | `TRADOVATE_DEVICE_ID` env var, stable per deployment |
| 19 | **One API connection per user** — a Tradovate Trader login ends the API session (and vice versa) | Single-session **broker gateway** owns the token and both websockets; product processes attach via local RPC. Ops rule: never log into Tradovate Trader with the bot's account while the bot runs |
| 20 | Auto-liquidation below the greater of $500 / 3% of initial margin; accounts not margined by 4:45 PM ET liquidated | Margin monitor blocks entries that don't fit free cash + buffer; 15:55 ET flatten keeps the account flat well before the deadline (§13) |
| 21–23 | Per-second/minute/hour rate caps → `429`; time-penalty tickets must be stored and re-submitted after the prescribed wait; caps may change without notice | Gateway budgeter: token-bucket per scope with ≥20% headroom, exponential backoff on 429, penalty-ticket persistence and replay |
| 24–25 | MD subscriptions throttled under load; responses may be coalesced across symbols or drop stale updates | `websocket.py` parses combined multi-symbol frames; the DOM book treats gaps as drop-and-resync events, never assumes frame continuity |
| 4 | Wash-trade prohibition (Rule 534) | Wash guard in `execution_guards`: no simultaneous opposite-side working orders in the same root or its micro/mini twin (MES↔ES, MNQ↔NQ, MCL↔QM, …) across all product processes |
| 9 | Back-month trading may require a risk change request | The resolver trades the front (active) month only; back months are never subscribed (§4) |
| 31 | Market data may not be redistributed, directly or in derived works | Grafana/Prometheus stay internal to the deployment; no MD-derived feeds are exposed externally |
| 32 | Every live account has an unlimited simulation account | Demo soak (roadmap ph. 8) and incubation fill-validation legs run on the sim environment (§12) |

The remaining attestation items (fees, community resources, third-party library
risk, etc.) are operational knowledge rather than architecture, but the
checklist itself is a **pre-live requirement** (§23) — the attestation must be
completed before an API key exists at all.

---

## 18. Component Map

```
src/
├── auth/
│   └── tradovate_auth.py ──── accessTokenRequest + renewal loop (~60 min),
│                              demo/live endpoint selection from mode switches
├── client/
│   ├── gateway.py ─────────── THE single Tradovate session (§17, attest. #19):
│   │                          owns token + trading/MD websockets, serves all
│   │                          product processes over local RPC; rate-limit
│   │                          budgeter (429 backoff, penalty-ticket replay)
│   ├── rest.py ────────────── Async REST: accounts, placeOrder, cancelOrder,
│   │                          liquidatePosition, cancelAllOrders (via gateway)
│   └── websocket.py ───────── Auto-reconnect WS (Tradovate frame protocol:
│                              open/heartbeat 'h' frames, JSON arrays; handles
│                              coalesced multi-symbol frames + stale-drop)
├── reference/
│   ├── volume_oi.py ───────── CME Volume & OI fetcher (per product slug)
│   ├── contract_resolver.py ─ picks active month, writes active_contracts,
│   │                          flags rolls
│   └── ff_calendar.py ─────── ForexFactory scraper → USD red-folder events
├── scheduling/
│   ├── reference_daemon.py ── APScheduler: 18:00 ET calendar, 18:30 ET vol/OI
│   ├── session_manager.py ─── open/close/flatten state machine (§6)
│   └── news_guard.py ──────── blackout window evaluation on every tick (§5)
├── market_data/
│   ├── orderbook.py ───────── DOM (depth-of-market) book, tick-indexed
│   └── ticker.py ──────────── quote/settlement snapshot
├── trading/
│   ├── signals.py ─────────── Signal enum: BUY / SELL / NEUTRAL   (ported)
│   ├── orders.py ──────────── Order model + Tradovate OrderManager (OSO
│   │                          brackets, isAutomated stamped on every order)
│   ├── position.py ────────── net position, avg px, realized/unrealized P&L
│   ├── risk.py ────────────── tick-native progressive trailing SL/TP (ported)
│   ├── price_action.py ────── EMA trend + V-bottom/V-top + re-test  (ported)
│   ├── order_flow.py ──────── strategy engine / central event hub  (ported)
│   └── incubator.py ───────── per-strategy paper mode inside live process (§12)
├── research/                  # the strategy factory (§8–§14)
│   ├── data_store.py ──────── historical bars, roll-stitched continuous series
│   ├── backtester.py ──────── event-driven replay, pessimistic fill model
│   ├── walkforward.py ─────── in/out folds, holdout confirmation, WF history
│   ├── montecarlo.py ──────── 2,500-iteration resampler, cones, ret/DD, RoR
│   ├── sizing.py ──────────── fixed-fractional x sweeps, joint multi-system calib
│   ├── diversification.py ─── correlation / linearity / combined-MC reports
│   └── gatekeeper.py ──────── lifecycle state machine G0→G6, sole promoter
├── audit/
│   └── reconciler.py ──────── orders/positions/fills/statement reconciliation (§16)
├── storage/
│   └── db.py ──────────────── SQLite access layer (WAL mode, one writer)
└── utils/
    ├── logger.py ──────────── structured logging, [SYMBOL] prefix
    └── metrics.py ─────────── Prometheus gauges/counters per product
```

The four `(ported)` modules keep their kraken logic; only their price arithmetic
changes (percent-based thresholds → tick-based where marked in config).

---

## 19. Directory Structure

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
│   │                          # strategy & research defaults      [EXISTS]
│   ├── products.yaml          # full mini/micro catalog + trade flags [EXISTS]
│   └── playbook/              # one G1 card per strategy module (§8) [EXISTS]
│       ├── README.md          # card schema + lifecycle wiring
│       └── <module>.yaml      # 23 cards mirroring strategies in config.yaml
│
├── docs/
│   ├── README.md              # this document                    [EXISTS]
│   └── Algorithmic trading system.pdf   # methodology source     [EXISTS]
│
├── src/                       # (see Component Map, §18)
│
├── data/
│   └── tradovate_bot.db       # SQLite (auto-created)
│
├── monitoring/                # prometheus.yml + grafana dashboards
└── logs/                      # one rotating log per product
```

---

## 20. Database Schema

```sql
-- ============ execution plane ============

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

-- ============ research plane ============

-- one row per (strategy, product) candidacy; append-only across retirements
CREATE TABLE strategy_lifecycle (
  id INTEGER PRIMARY KEY, strategy TEXT, product TEXT,
  state TEXT NOT NULL,               -- idea|limited_test|walk_forward|monte_carlo|
                                     -- incubation|live|retired
  entered_state_at TEXT NOT NULL,
  gate_evidence_run_id INTEGER,      -- FK to the run that justified the transition
  retired_reason TEXT
);

CREATE TABLE backtest_runs (
  id INTEGER PRIMARY KEY, strategy TEXT, product TEXT, kind TEXT,  -- limited|wf_fold
  params_json TEXT, date_from TEXT, date_to TEXT,
  net_profit REAL, max_drawdown REAL, trades INTEGER,
  largest_loss REAL, fill_flags_json TEXT, created_at TEXT
);

CREATE TABLE walkforward_folds (
  run_id INTEGER, fold INTEGER, in_from TEXT, in_to TEXT, out_from TEXT, out_to TEXT,
  params_json TEXT, out_net_profit REAL,
  PRIMARY KEY (run_id, fold)
);

CREATE TABLE monte_carlo_runs (
  id INTEGER PRIMARY KEY, strategy TEXT, product TEXT, source_run_id INTEGER,
  iterations INTEGER, fixed_fraction_x REAL,
  ret_dd_ratio REAL, median_max_dd REAL, p95_max_dd REAL,
  risk_of_ruin REAL, prob_profit_1y REAL,
  cone_json TEXT,                    -- avg / top10 / low10 equity paths
  created_at TEXT
);

CREATE TABLE incubation_equity (
  strategy TEXT, product TEXT, ts TEXT, paper_pnl REAL, cum_pnl REAL,
  PRIMARY KEY (strategy, product, ts)
);

CREATE TABLE live_vs_expected (
  strategy TEXT, product TEXT, trade_date TEXT,
  live_cum_pnl REAL, expected_avg REAL, band_low10 REAL, band_top10 REAL,
  quitting_point REAL, breach INTEGER DEFAULT 0,
  PRIMARY KEY (strategy, product, trade_date)
);

CREATE TABLE reconciliation_log (
  id INTEGER PRIMARY KEY, ts TEXT, product TEXT, check_name TEXT,
  ok INTEGER, detail_json TEXT, acknowledged_at TEXT
);
```

SQLite runs in WAL mode: the reference daemon is the only writer to reference
tables; product processes write only their own `fills` rows; the research plane
writes only research tables.

---

## 21. Configuration Reference

See [`config/config.yaml`](../config/config.yaml) (inline-documented). For a
non-technical, knob-by-knob walkthrough with worked examples, see
["The control panel"](README_v1_plain-english.md#the-control-panel-configconfigyaml-knob-by-knob)
in the plain-English README. Summary:

| Block | Key settings |
|-------|--------------|
| `mode` | `dry_run`, `live_trading` — the two account-level switches (§2) |
| `tradovate` | demo/live REST + WS URLs; credentials via env vars only |
| `session` | `open: 08:00`, `close: 16:00` ET, `flatten_buffer_minutes: 5`, Sun–Fri |
| `news_guard` | USD + high impact, 15 min before/after, daily 18:00 ET refresh, `position_policy` |
| `contract_resolver` | daily 18:30 ET, `max_volume_and_oi` rule, 48 h staleness guard |
| `shared_services` | structure engine, levels service, regime classifier, strategy router (arbitration, §7), trailing-exit engine, execution guards |
| `strategies` | 23 playbook modules with skill number, tier, priority, and `enabled` flags — `enabled` now means "eligible for the factory"; `strategy_lifecycle` (DB) decides what trades |
| `playbook/` | one card per module — the G1 artifact (§8): goal, mechanical rules, ambiguity ledger; params stay in `strategies.<module>.params` (one source of truth each) |
| `research` | gate thresholds — see below |
| `risk_operations` | operational switches (`flatten_on_disconnect`, one strategy per product, portfolio circuit breaker) |

New `research:` block:

```yaml
research:
  # Gate thresholds (G2–G5)
  wf_efficiency_min: 0.5             # out-of-sample vs in-sample profit rate
  wf_holdout_years: 3                # untouched tail for in/out confirmation
  mc_iterations: 2500
  mc_ret_dd_min: 2.0                 # book's acceptance floor
  mc_risk_of_ruin_max: 0.10
  incubation_min_days: 90            # 3 months floor, 6 months typical
  incubation_review: monthly
  max_new_strategy_correlation: 0.6  # vs any live strategy, else hold at G5
  quit_multiplier: 1.0               # quitting point = p95 MC drawdown × this
  next_best_alternative_months: 6
```

Per-product `risk:` blocks in `products.yaml` (§13) gain a `sizing:` sub-block:

```yaml
    sizing:
      model: fixed_fractional        # fixed | fixed_fractional
      fixed_fraction_x: null         # null = calibrated by research/sizing.py
      max_drawdown_pct: 45           # constraint for x calibration
      max_risk_of_ruin_pct: 10
      warmup_trades: 20              # trade 1 contract until this many live trades
```

`risk_operations` gains the portfolio circuit breaker:

```yaml
risk_operations:
  flatten_on_disconnect: true
  max_concurrent_strategies_per_product: 1
  portfolio_daily_loss_limit_usd: 500   # flatten + halt ALL products
```

Strategy parameter overrides (any `strategies.<module>.params` key) nest under
`overrides:` on the product entry in `products.yaml`.

---

## 22. Build Roadmap

| Phase | Deliverable | Depends on |
|-------|-------------|-----------|
| 1 | `storage/db.py` + schema, `config` loaders (this design's contracts) | — |
| 2 | `reference/volume_oi.py` + `contract_resolver.py` (+ CLI: `python -m reference.resolver --once`) | 1 |
| 3 | `reference/ff_calendar.py` + `reference_daemon.py` (APScheduler) | 1 |
| 4 | `auth/` + `client/` — Tradovate token, single-session gateway (rate budgeter, penalty-ticket replay), REST, WS frame protocol, DOM subscribe on demo | — |
| 5 | `scheduling/session_manager.py` + `news_guard.py` with unit tests (freeze-time) | 1,3 |
| 6 | Port `trading/` engine from kraken (tick-quantized), `main.py` wired end-to-end in `dry_run` | 2,4,5 |
| 7 | `launcher.py` multi-product + monitoring stack | 6 |
| 8 | Demo-account soak (dry_run=false, live_trading=false) on MES/MNQ | 7 |
| 9 | `research/data_store.py` — roll-stitched history from `volume_oi_history` + bar ingestion | 2 |
| 10 | `research/backtester.py` with pessimistic fill model + fill-flag rejection | 6,9 |
| 11 | `research/walkforward.py` + `walkforward_folds`/`backtest_runs` persistence | 10 |
| 12 | `research/montecarlo.py` + cones + `monte_carlo_runs` | 11 |
| 13 | `research/gatekeeper.py` + `strategy_lifecycle` + launcher/order-router enforcement | 12 |
| 14 | `trading/incubator.py` (paper mode in live process) + monthly review job | 13 |
| 15 | `research/sizing.py` fixed-fractional calibration; wire into `risk.py` | 12 |
| 16 | `audit/reconciler.py` + reconciliation metrics + session-open gate | 7 |
| 17 | `live_vs_expected` pipeline + Grafana overlay & cone dashboards + weekly review report | 13,16 |
| 18 | `research/diversification.py` portfolio report + portfolio circuit breaker | 15,17 |

Suggested first factory run: `order_flow_scalp` (already live-candidate) through
G2–G4 retroactively — it currently sits at `live`-by-default and is exactly the
kind of untested-by-this-pipeline strategy the research plane exists to catch.

---

## 23. Pre-Live Checklist

Account / infrastructure:

- [ ] `dry_run: false` and `live_trading: true` set intentionally; launcher run with `--confirm-live`
- [ ] Only intended products have `trade: true`
- [ ] `active_contracts` fresh (< 24 h) for every enabled product
- [ ] Today's news events present in `news_events` (check count > 0 on CPI/NFP days)
- [ ] Observed one full 15:55 ET flatten on the demo account
- [ ] `stop_loss_usd` × products ≤ capital you accept losing in one session
- [ ] Tradovate API access is on a dedicated sub-account with only trading permissions
- [ ] Tradovate 32-point API self-attestation completed; API key scope limited to trading (§17)
- [ ] `isAutomated: true` verified on demo orders
- [ ] Standing ops rule agreed: nobody logs into Tradovate Trader with the bot's
      account while the bot runs — it kills the API session (attestation #19)
- [ ] Reconciler green (`bot_reconciliation_ok = 1`) for 5 consecutive sessions on demo

Per strategy being promoted:

- [ ] Playbook card complete (`config/playbook/<module>.yaml`): `ambiguities_open`
      empty, card commit hash recorded as G1 evidence on the lifecycle row
- [ ] `strategy_lifecycle` state is `incubation` with ≥ `incubation_min_days` elapsed
- [ ] Walk-forward out-of-sample equity met the strategy's written goal; in/out
      periods confirmed on the untouched holdout
- [ ] Monte Carlo run stored: ret/DD ≥ 2.0, risk of ruin ≤ 10%, `cone_json` present
- [ ] Incubation equity above the lower-10% band at the last monthly review
- [ ] Quitting point computed, written to `live_vs_expected.quitting_point`
- [ ] `fixed_fraction_x` calibrated (or `warmup_trades` forces 1-lot start)
- [ ] Correlation vs every live strategy ≤ `max_new_strategy_correlation`
- [ ] Operator has answered the weekly review questions for the final incubation month

And the standing reminder the book closes on: no strategy lasts forever — the
factory (G1→G4 pipeline) must keep running while the current strategies trade,
because the semi-annual review needs a bench to draw from.

---

*Python 3.11+ · Tradovate REST/WS API · CME Globex · SQLite + APScheduler ·
Prometheus + Grafana · Methodology: K. Davey, "Building Winning Algorithmic
Trading Systems" (Wiley, 2014)*
