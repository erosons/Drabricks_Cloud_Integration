# Tradovate CME Futures AI Trading Bot — Architecture v1

**What changed from v0 → v1:** v0 (see [README.md](README.md)) designed the *execution
plane* — process-per-product isolation, contract resolution, news guard, session
management, tick-native risk. v1 upgrades the architecture with the strategy
development methodology from Kevin Davey's *Building Winning Algorithmic Trading
Systems* (Wiley, 2014 — `docs/Algorithmic trading system.pdf`): every strategy must
now earn its way to live capital through a **gated lifecycle** (limited test →
walk-forward → Monte Carlo → incubation → live), position sizing becomes
**fixed-fractional and Monte Carlo-calibrated**, and live strategies are monitored
against their **statistical expectation bands** with an explicit quitting point.

The core insight adopted from the book: *the execution engine is not the edge — the
validation pipeline is.* Davey reports needing 100–200 tested ideas to find one worth
trading. This architecture therefore treats the 23 playbook strategy modules in
`config.yaml` not as features to switch on, but as **candidates in a strategy
factory**, most of which are expected to be discarded.

---

## Table of Contents

1. [Architecture Overview (v1)](#1-architecture-overview-v1)
2. [The Strategy Lifecycle — Gates G0→G6](#2-the-strategy-lifecycle--gates-g0g6)
3. [Research Plane: Backtest Engine](#3-research-plane-backtest-engine)
4. [Walk-Forward Analysis](#4-walk-forward-analysis)
5. [Monte Carlo Analysis](#5-monte-carlo-analysis)
6. [Incubation](#6-incubation)
7. [Position Sizing & Money Management](#7-position-sizing--money-management)
8. [Diversification Controls](#8-diversification-controls)
9. [Live Monitoring vs Expectation](#9-live-monitoring-vs-expectation)
10. [Reconciliation & Fill-Integrity Audit](#10-reconciliation--fill-integrity-audit)
11. [Execution Plane (carried from v0)](#11-execution-plane-carried-from-v0)
12. [Component Map (v1 additions)](#12-component-map-v1-additions)
13. [Database Schema (v1 additions)](#13-database-schema-v1-additions)
14. [Configuration Changes](#14-configuration-changes)
15. [Build Roadmap (v1)](#15-build-roadmap-v1)
16. [Pre-Live Checklist (v1)](#16-pre-live-checklist-v1)

---

## 1. Architecture Overview (v1)

v1 splits the system into two planes sharing one SQLite contract of record:

```
┌─────────────────────────── RESEARCH PLANE (new) ───────────────────────────┐
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
┌────────────────────────── EXECUTION PLANE (v0, upgraded) ──────────────────┐
│  launcher.py ─► one process per product with trade: true                   │
│      each process runs its regime-routed strategy module ONLY if the       │
│      module's lifecycle_state permits it (live, or incubation → paper)     │
│                                                                            │
│  reference_daemon.py ─► 18:00 ET news scrape · 18:30 ET CME Vol/OI         │
│  session_manager ─► 08:00–16:00 ET · unconditional 15:55 flatten           │
│  reconciler (new) ─► statements vs fills · orphan orders · flat checks     │
│  monitor (new)    ─► live equity vs Monte Carlo expectation bands          │
└────────────────────────────────────────────────────────────────────────────┘
```

### New design decisions

| Decision | Rationale (from the book) |
|----------|---------------------------|
| **Lifecycle gate, not an `enabled` flag** | An `enabled: true` edit must not be able to put an unvalidated strategy on live capital. The gate keeper enforces state transitions; config can only *request* them. |
| **Pessimistic fill model everywhere** | Davey's rule: assume a limit order fills only if price *penetrates* it (touch-fills happen only ~5–20% of the time live). Backtests that buy the low / sell the high of bars are rejected automatically. Live results should then only beat the backtest. |
| **Incubation is a first-class runtime mode** | 3–6 months of paper-tracking on unseen live data before capital, evaluated monthly like an extra out-of-sample period. Catches development mistakes (overfit, hindsight bias) that no backtest can. |
| **Sizing derived from Monte Carlo, capped by config** | Fixed-fractional `N = int(x · Equity / LargestLoss)` with `x` chosen from Monte Carlo sweeps subject to max-drawdown and risk-of-ruin ceilings — never from a single historical equity curve. |
| **Every live strategy has a pre-committed quitting point** | Decided *before* going live from the Monte Carlo drawdown distribution. Hitting it retires the strategy regardless of any narrative. Prevents "doubling down" on a broken system. |
| **Daily reconciliation is mandatory** | Davey's live-trading incident: an order that should have auto-cancelled rested overnight and filled into a rogue position, discovered 30+ hours late. The reconciler exists to find that class of failure within minutes, not days. |

---

## 2. The Strategy Lifecycle — Gates G0→G6

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
| **G1 → limited_test** | Is the idea worth computer time? | Written goal/objective for the strategy; entry & exit fully mechanical (no discretionary or repainting inputs — the playbook's priority-3 ambiguities must be resolved here) |
| **G2 → walk_forward** | Does a quick, cheap test show an edge? | Limited backtest (recent 1–2 y, 1 contract, pessimistic fills, costs included) shows positive expectancy; no red-flag artifacts (§3) |
| **G3 → monte_carlo** | Does the edge survive out-of-sample? | Walk-forward efficiency ≥ 50% (out-of-sample profit rate vs in-sample); combined out-of-sample equity meets the strategy's stated goal; in/out periods chosen on holdout data, not optimized (§4) |
| **G4 → incubation** | What are the realistic risk odds? | Monte Carlo (2,500 iterations) annual **return / max drawdown ≥ 2.0**; risk of ruin ≤ 10%; median max drawdown within the product's tolerance (§5) |
| **G5 → live** | Did it work on data nobody touched? | 3–6 months incubation; paper equity within the Monte Carlo expectation cone (above the lower-10% band at review); no unresolved fill-model discrepancies (§6) |
| **G6 (ongoing)** | Should it keep trading? | Live equity above quitting point; monthly review answers "no reason to stop" (§9). Semi-annual *next-best-alternative* review may also replace it (§9) |

Rules enforced by the **gate keeper** (`research/gatekeeper.py`):

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

## 3. Research Plane: Backtest Engine

New package `src/research/`. The backtester replays historical bars/DOM through the
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
  every fill; the reconciler later verifies live slippage against this model (§10).

**Data store**: continuous per-product history stitched from individual contract
months using the roll dates the resolver already records in `volume_oi_history` —
backtests roll exactly when the live bot would have rolled.

---

## 4. Walk-Forward Analysis

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
  sizing (§7).

---

## 5. Monte Carlo Analysis

`research/montecarlo.py` — the trade list from the walk-forward out-of-sample curve
is resampled (order-randomized) for **2,500 iterations** per scenario, producing
distributions rather than a single historical path:

| Output | Used for |
|--------|----------|
| Annual return / max drawdown ratio | **Gate G4: must be ≥ 2.0** (below that, the risk isn't paying) |
| Median & 95th-percentile max drawdown | Product risk-block sanity + quitting point (§9) |
| Risk of ruin (equity ≤ quitting-point capital) | Gate G4: ≤ 10% |
| Probability of profit in one year | Diversification comparisons (§8) |
| Expectation cone (average / top-10% / lower-10% equity paths) | Incubation & live tracking bands (§6, §9) |
| Return/DD as a function of fixed fraction `x` | Position-sizing calibration (§7) |

All runs are persisted (`monte_carlo_runs`) — the bands drawn on live dashboards
must be reproducible from a stored run ID, not recomputed ad hoc.

---

## 6. Incubation

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

## 7. Position Sizing & Money Management

v0 sized every trade at a static `max_contracts`. v1 keeps that as the hard cap but
introduces the book's **fixed-fractional** model as the sizing engine:

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

Principles inherited verbatim from the book, encoded as invariants:

- New live strategies always start at **1 contract** regardless of formula output
  (`sizing.warmup_trades` before formula sizing activates).
- Sizing never rescues a losing strategy and can destroy a winning one — hence the
  constraint-first calibration and the absolute config cap.
- Martingale/no-limit progressions are structurally impossible: `N` is a pure
  function of equity, never of recent losses (playbook skill-5 verdict upheld).

---

## 8. Diversification Controls

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
- Portfolio-level `daily_loss_limit_usd` (new, in `risk_operations`) sits above the
  per-product limits: breaching it flattens and halts *all* products for the day.

---

## 9. Live Monitoring vs Expectation

v0 monitored infrastructure (session state, blackouts, rolls). v1 adds *statistical*
monitoring: is the live strategy still the strategy we validated?

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
- Are live fills comparable to the fill model (slippage delta from §10)?
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

## 10. Reconciliation & Fill-Integrity Audit

New module `src/audit/reconciler.py`, born directly from the book's week-9 live
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

Prometheus additions: `bot_orphan_orders_total`, `bot_position_mismatch`,
`bot_slippage_ticks_actual`, `bot_reconciliation_ok` (gauge per product; the
session manager will not leave CLOSED while it is 0).

---

## 11. Execution Plane (carried from v0)

Unchanged and normative — full detail in [README.md](README.md):

- **Three-switch safety model** (`dry_run` / `live_trading` / per-product `trade`)
  plus the `--confirm-live` launcher gate. v1 adds the lifecycle gate *behind* these:
  all four switches on still won't trade a strategy that isn't `live` in
  `strategy_lifecycle`.
- **Process-per-product isolation**, shared **reference daemon** (18:00 ET
  ForexFactory scrape, 18:30 ET CME Volume & OI), SQLite contract of record.
- **Active-contract resolver** with 48 h staleness refusal and roll handling.
- **News guard** blackouts (USD red-folder, −15/+15 min, fail-closed when stale).
- **Session manager** 08:00→16:00 ET, unconditional 15:55 flatten watchdog,
  flatten-on-disconnect dead-man's switch.
- **Trade decision pipeline** gates F1–F3 + the two-layer signal engine.
- **Tick-native risk math** and per-product `risk:` blocks in `products.yaml`
  (no global fallback; validation failure without one).

---

## 12. Component Map (v1 additions)

```
src/
├── research/                      # NEW — the strategy factory
│   ├── data_store.py              # historical bars, roll-stitched continuous series
│   ├── backtester.py              # event-driven replay, pessimistic fill model
│   ├── walkforward.py             # in/out folds, holdout confirmation, WF history
│   ├── montecarlo.py              # 2,500-iteration resampler, cones, ret/DD, RoR
│   ├── sizing.py                  # fixed-fractional x sweeps, joint multi-system calib
│   ├── diversification.py         # correlation / linearity / combined-MC reports
│   └── gatekeeper.py              # lifecycle state machine G0→G6, sole promoter
├── audit/                         # NEW
│   └── reconciler.py              # orders/positions/fills/statement reconciliation
├── trading/
│   ├── incubator.py               # NEW — per-strategy paper mode inside live process
│   └── (v0 modules unchanged)
└── (auth/, client/, reference/, scheduling/, market_data/, storage/, utils/ as v0)
```

---

## 13. Database Schema (v1 additions)

```sql
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

---

## 14. Configuration Changes

New top-level `research:` block in `config.yaml`:

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

Per-strategy in `strategies.<module>`: `enabled:` is superseded by the lifecycle —
it now means "eligible for the factory," while `strategy_lifecycle` (DB) decides
what actually trades. Per-product `risk:` blocks in `products.yaml` gain:

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
  portfolio_daily_loss_limit_usd: 500   # NEW — flatten + halt ALL products
```

---

## 15. Build Roadmap (v1)

Phases 1–8 from v0 (execution plane) are unchanged and remain first — the research
plane needs the same strategy modules, shared services, and DB the live path uses.

| Phase | Deliverable | Depends on |
|-------|-------------|-----------|
| 9  | `research/data_store.py` — roll-stitched history from `volume_oi_history` + bar ingestion | v0 ph.2 |
| 10 | `research/backtester.py` with pessimistic fill model + fill-flag rejection | 9, v0 ph.6 |
| 11 | `research/walkforward.py` + `walkforward_folds`/`backtest_runs` persistence | 10 |
| 12 | `research/montecarlo.py` + cones + `monte_carlo_runs` | 11 |
| 13 | `research/gatekeeper.py` + `strategy_lifecycle` + launcher/order-router enforcement | 12 |
| 14 | `trading/incubator.py` (paper mode in live process) + monthly review job | 13 |
| 15 | `research/sizing.py` fixed-fractional calibration; wire into `risk.py` | 12 |
| 16 | `audit/reconciler.py` + reconciliation metrics + session-open gate | v0 ph.7 |
| 17 | `live_vs_expected` pipeline + Grafana overlay & cone dashboards + weekly review report | 13, 16 |
| 18 | `research/diversification.py` portfolio report + portfolio circuit breaker | 15, 17 |

Suggested first factory run: `order_flow_scalp` (already live-candidate) through
G2–G4 retroactively — it currently sits at `live`-by-default and is exactly the
kind of untested-by-this-pipeline strategy v1 exists to catch.

---

## 16. Pre-Live Checklist (v1)

Everything from v0, plus per strategy being promoted:

- [ ] `strategy_lifecycle` state is `incubation` with ≥ `incubation_min_days` elapsed
- [ ] Walk-forward out-of-sample equity met the strategy's written goal; in/out
      periods confirmed on the untouched holdout
- [ ] Monte Carlo run stored: ret/DD ≥ 2.0, risk of ruin ≤ 10%, `cone_json` present
- [ ] Incubation equity above the lower-10% band at the last monthly review
- [ ] Quitting point computed, written to `live_vs_expected.quitting_point`
- [ ] `fixed_fraction_x` calibrated (or `warmup_trades` forces 1-lot start)
- [ ] Correlation vs every live strategy ≤ `max_new_strategy_correlation`
- [ ] Reconciler green (`bot_reconciliation_ok = 1`) for 5 consecutive sessions on demo
- [ ] Operator has answered the weekly review questions for the final incubation month

And the standing reminder the book closes on: no strategy lasts forever — the
factory (G1→G4 pipeline) must keep running while the current strategies trade,
because the semi-annual review needs a bench to draw from.

---

*Python 3.11+ · Tradovate REST/WS API · CME Globex · SQLite + APScheduler ·
Prometheus + Grafana · Methodology: K. Davey, "Building Winning Algorithmic
Trading Systems" (Wiley, 2014)*
