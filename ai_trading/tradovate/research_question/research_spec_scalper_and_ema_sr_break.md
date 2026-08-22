# Research Spec: order_flow_scalp Final Test + ema_sr_break Validation

Two workstreams. Workstream A (scalper) is a bounded autopsy — cheap, terminal, run first or in parallel. Workstream B (ema_sr_break) is the promotion path toward G3 and is the priority deliverable.

All pass/fail thresholds in this document are **pre-committed**: they are decided now, before any run. Do not revise a threshold after seeing results. Persist every run to `backtest_runs` / `research_results` with a `study` tag so `v_research_summary` ranks them. Use the existing dev set only (data < 2026-05-20); the holdout remains sealed except where Stage B5 explicitly says otherwise.

---

## Workstream A — order_flow_scalp: final autopsy (bounded, terminal)

**Question:** Is there any configuration in which the two signal layers cooperate outside news spikes — or is the strategy dead on CME?

**Scope guard:** This workstream is capped at the two studies below. No new filters, no new parameters, no "one more idea" beyond them. Any outcome other than an explicit PASS closes the strategy's file.

### A0 — Signal predictiveness study (run first; cheapest, most decisive)

Method:
- Replay the 9-month MES tick dev set through the order book. No trading, no brackets.
- At every tick where the L1 imbalance signal fires (current confidence threshold), record: direction, timestamp, mid price.
- Measure forward mid-price change at +5s, +15s, +30s, +60s after each signal.
- Exclude signals inside the 15-minute news-guard windows (use the same calendar logic the live guard will use; if no historical calendar is wired, exclude ±15 min around 08:30 and 10:00 ET as a proxy, and note this in results).
- Report: signal count, hit rate (sign of forward move matches signal direction) and mean signed forward move in ticks, per horizon. Compare against the unconditional baseline (same stats sampled at random ticks).

Pre-committed verdict:
- **PASS:** at ≥1 horizon, hit rate ≥ 53% AND mean signed forward move ≥ 0.5 tick above baseline, with ≥ 5,000 non-news signals in the sample.
- **FAIL:** anything less. On FAIL: **stop. Do not run A1.** Record verdict `signal_not_predictive` and close the strategy (see Closure).

### A1 — L2 relaxation ladder (only if A0 passes)

Method: run the full 9-month MES tick backtest (existing pessimistic harness, unchanged fill rules, commissions $1.10/side) four times:

| Rung | Layer-2 configuration |
|---|---|
| 1 | Full truth table (current) — baseline, expected ~0 trades |
| 2 | Trend agreement only (drop exhaustion requirement) |
| 3 | Exhaustion only (drop trend requirement) |
| 4 | No layer 2 (L1 imbalance alone) |

For each rung record: trade count, net P&L after fees, win rate, expectancy per trade, and entry-time histogram by ET hour.

Pre-committed verdict (evaluated per rung):
- **PASS:** ≥ 100 trades over the 9 months AND positive net expectancy after commissions AND < 25% of entries inside news-guard windows.
- **FAIL:** all rungs miss any of the three conditions.

### A closure

- On any FAIL: set lifecycle to `research_closed` with reason (`signal_not_predictive` or `layers_never_cooperate`), demote/remove any remaining live-by-default rows, and write a short postmortem note into the research results: "Kraken-origin microstructure signal does not transfer to CME" (the risk the playbook card itself listed).
- On PASS at some rung: do **not** promote. The passing rung becomes a new candidate configuration that must enter Workstream B's pipeline from Stage B1 as if it were a new strategy.

---

## Workstream B — ema_sr_break: validation toward G3 (priority)

**Question:** Is the tournament winner a real edge (plateau) or the lucky survivor of 22 entrants (needle)?

Baseline: the tournament's winning parameter set on the bar cache (Davey rules), both MES and MNQ, 9-month dev set. Freeze and record this baseline config as `B_base` before starting.

### B1 — Parameter robustness grid (the G2 move; run first)

Method:
- Identify the strategy's tunable parameters (expected: fast/slow EMA lengths, S/R lookback, breakout threshold, stop distance, target multiple — enumerate whatever the card actually exposes).
- Build a grid: each parameter at 5 values — baseline, ±1 step, ±2 steps — where a "step" is ~10–20% of the baseline value (round to natural units). Full cartesian product if ≤ ~2,000 combos on the bar harness; otherwise one-at-a-time sweeps plus a fractional grid around the baseline.
- Run every combo on both MES and MNQ over the dev set. Persist all runs tagged `b1_grid`.

Pre-committed verdict:
- **PASS (plateau):** ≥ 60% of the grid cells within ±1 step of baseline are net-positive after fees on both products, AND the baseline is not the single best cell by a wide margin (best cell ≤ 2× baseline expectancy).
- **FAIL (needle):** profitability collapses (majority of adjacent cells negative) one step away from baseline on either product. On FAIL: record `overfit_needle`, close the strategy, and promote the next tournament candidate for the same treatment — do not tune the needle into a plateau by hand.

### B2 — Distribution sanity (cheap; runs off B1's baseline output)

Using `B_base` trade lists on both products, check:
- **Time-of-day:** no single ET hour contains > 40% of entries; < 25% of entries inside news-guard windows.
- **Concentration:** no single month contributes > 50% of total net P&L; removing the single best trade leaves the strategy net-positive.
- **Cross-product coherence:** MES and MNQ monthly P&L signs agree in ≥ 6 of 9 months.

**FAIL** on any check: treat as `fragile_distribution`; investigate before proceeding, and if the concentration is structural (e.g., one freak week is the entire edge), close.

### B3 — Cost stress

Rerun `B_base` (both products) under: (a) slippage × 2, (b) commissions × 1.5, (c) both.
- **PASS:** net-positive on both products under (c).
- **FAIL:** close as `no_cost_margin`.

### B4 — Walk-forward

Method:
- Folds over the dev set: tune on a 3-month window (grid from B1, pick best cell by expectancy), trade the following 1 month untouched. Slide by 1 month → 6 out-of-sample months per product.
- Persist per-fold results tagged `b4_wf`.

Pre-committed verdict:
- **PASS:** aggregate out-of-sample net P&L positive on both products; ≥ 4 of 6 folds non-negative per product; no fold loses more than 2× the average winning fold's gain.
- **FAIL:** close as `not_findable_in_advance`.

### B5 — Holdout (one shot; requires explicit human approval before running)

- Only if B1–B4 all PASS. Freeze the configuration (the B1 baseline, not per-fold retunes) and write it into the results table **before** the run.
- Run once on data ≥ 2026-05-20 using `--holdout`, both products. **Do not rerun, do not tweak-and-retry.** A second attempt permanently contaminates the holdout.
- **PASS:** holdout expectancy per trade falls within the Monte Carlo 90% band implied by the dev-set trade distribution (compute the band from dev-set win rate + payoff distribution before the run and record it).
- **FAIL:** close as `holdout_collapse`; the holdout period is burned for this strategy family.

### B6 — Demo soak (on PASS of B5)

- Promote lifecycle to demo-eligible. Two weeks of session days through the real Tradovate order path, params frozen.
- Compare live fill quality, trade frequency, and expectancy against the backtest's Monte Carlo band. Inside the band → G3 review for small live size. Outside → back to research with the live-vs-sim delta documented.

---

## Execution order

1. **B1** (priority — the bar harness makes it fast)
2. **A0** (cheap, can run in parallel)
3. A1 only if A0 passes; B2/B3 as soon as B1 passes
4. B4 → human check-in → B5 → B6

## Standing rules

- Thresholds above are frozen. If a result is borderline, it fails.
- Every run persists to the research tables with its study tag; nothing lives only in logs.
- Any strategy closure includes demoting associated live-by-default lifecycle rows.
- Report back after B1 and A0 with the verdicts and the supporting numbers before proceeding further.
