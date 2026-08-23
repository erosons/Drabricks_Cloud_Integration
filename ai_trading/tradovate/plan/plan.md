# momentum_dollar_trail — Frozen Config, Four-Week Findings, and the Monday Demo Plan

**Date:** 2026-08-23 (Sunday) · **Demo starts:** Monday 2026-08-24, 08:00 ET
**Strategy:** `momentum_dollar_trail` · **Frozen config:** $20 price trail / $100 stop (MES: the two merge into a **pure 20-point trailing stop**)
**Status:** DEMO ONLY. This strategy has **not** passed gates G2–G4. The runner refuses `live_trading: true`.

---

## 1. The frozen configuration

| Parameter | Value | Meaning on MES |
|---|---|---|
| `move_trigger_ticks` | 2 | entry when two consecutive 1m closes move the same direction, ≥ 2 ticks combined |
| `trail_dollars` | $20.00 (price) | stop trails the best price since entry by 20 points |
| `max_loss_usd` | $100.00 | = 20 points — identical to the trail, so stop ≡ trail from entry |
| Exit | trail or 15:55 ET flatten | no profit target; always-in re-entry allowed |
| Size | 1 contract | LiveExecutor one-bracket guard |

Config lives in `config/config.yaml` (`strategies.momentum_dollar_trail`). The MES risk block was raised **for the demo**: `stop_loss_usd 50→100`, `daily_loss_limit_usd 150→300` — both marked in `products.yaml` and **must be reverted before any `live_trading: true`**.

How this config was reached: operator-driven iteration $5 → $30 → $20 → $40 → $50 → $100 stops across dev and holdout data. Every widening cut the trade count and the loss; this is the least-bad point found (holdout: **−$4.93/trade** vs −$8.13 at $40, −$7.88 at the original $5).

---

## 2. The four-week holdout walk — what was seen

All four weeks run at the frozen config, MES, pessimistic fill model ($1.10/side, 2-tick slippage). Day pages are published as artifacts; every run summarized here was inspected trade by trade.

| Week | Character | Trades | Net |
|---|---|---:|---:|
| Jul 27 – 31 | crash + recovery (~115-pt day, rebounds) | ~31 | **+$1,529.30** |
| Aug 3 – 7 | ordinary (two mild trends, three quiet days) | 21 | +$180.05 |
| Aug 10 – 14 | quiet range all week | 16 | **−$532.70** |
| Aug 17 – 21 | steady trend early, quiet finish | 14 | +$376.70 |
| **Four weeks** | | ~82 | **+$1,553** |

Context that must not be forgotten: the **full 65-session holdout nets −$2,076** at this config. These four weeks were the friendliest stretch of the tape; the nine prior weeks sum to ≈ −$3,600.

### What drove profitability
1. **Sustained multi-hour directional legs.** Every large win was a ride: +$415 (264 min, Jul 29 collapse), +$479 (final-hour capitulation, Jul 29), +$337 (257 min, Jul 31 recovery), +$233 (251 min, Jul 30), +$198 (single-trade day, Aug 17). The 20-point leash survives ordinary pullbacks that shook out every narrower config.
2. **Volatility expansion after compression.** The money arrived when range expanded — the crash week, the post-crash recovery, the steady Aug 17–19 trend. Quiet→expanding transitions are this strategy's entire edge surface.
3. **Low trade count = low friction.** 4–8 trades/day at this width vs 20+ at $40 and 150+ at the original $5. Fees fell from ~$60/day to ~$13/day. Half the improvement across the widening series was simply paying the round-trip toll less often.
4. **Single-trade days.** On cleanly trending days (Aug 17, Aug 18) the runner entered once near the open and held to the close — the strategy at its best is a mechanical day-length trend hold.

### What drove loss
1. **Quiet range sessions — the baseline bleed.** ~−$58/session whenever no 20-point move develops (Aug 10–14: five sessions, five losses, zero rides). Positions die slowly (~90-minute holds wandering back through the trail), not violently. This regime dominates the holdout's 65 sessions and produces its negative aggregate.
2. **V-turn double-taps.** At sharp reversals the always-in entry is wrong twice in minutes: the old position stops, the flip entry stops (−$99 in 3 minutes, Jul 28; −$194 midday Jul 29). Full stops at this width are ~$100 each plus slippage.
3. **The entry has no information.** Two 1-minute closes in the same direction fires ~4–8×/day with identical confidence on trend days and range days. Every loss category traces to this: the exit machinery works exactly as designed; the entry cannot tell which day it is.
4. **Trail giveback.** Wide trail = wide giveback: winners routinely surrendered 20 points ($100) from their peak (Jul 30's ride gave back most of a 30-point open profit before exiting).

**One-line identity:** this config is a *volatility-expansion harvester with no off-switch* — it prints in expansion weeks and bleeds through quiet ones, and across three unseen months the quiet ones won (−$2,076).

---

## 3. Monday demo plan (2026-08-24 →)

### Purpose — in order
1. **Order-path rehearsal** (the long-pending market demo): first-ever live loop of Databento data → signal → Tradovate DEMO OSO bracket → stop modifications → fills via `user/syncrequest` → SQLite `fills` → Grafana. Every layer built since the Databento migration gets exercised under real market conditions.
2. **Live-vs-sim measurement:** compare demo fills against the pessimistic model (entry slippage on marketable limits, stop-fill quality, modify latency). This calibrates the fill model for *all future* strategies.
3. **Live regime observation** of the strategy itself — with zero expectation of profit (see risks).

### How to run
```bash
# config/config.yaml: mode.dry_run: false, live_trading: false  (DEMO)
set -a && source .env && set +a
python -m src.reference.contract_resolver --once     # fresh active contract
cd monitoring && docker compose up -d && cd ..       # Grafana on :3000
python scripts/demo_momentum_trail.py                # the rehearsal bot
```
The runner (`src/trading/trail_runner.py`, launched by `scripts/demo_momentum_trail.py`):
- refuses `live_trading: true` and refuses `dry_run: true`
- reuses the proven order path (`main._attach_order_path`: startup position check, user/syncrequest gate, fill persistence, trading-socket watchdog)
- entries: marketable limit 2 ticks through the signal close, OSO bracket stop 20 pts away; trail ratchets once per 1m bar via `modify_stop`; unconditional 15:55 ET flatten
- signal parity with the research sim is unit-tested (`tests/test_trail_runner.py`; 202 tests total passing)

### Safety rails
- **Demo account only** — hard-coded refusal of live mode.
- 1 contract; one-bracket guard; server-side stop resting at the exchange at all times.
- `daily_loss_limit_usd: 300` (worst observed day at this config: −$336).
- Watchdog stops the bot if the fill stream is lost; SIGINT flattens cleanly.
- Rollback: `Ctrl-C`, then flatten manually in Tradovate Trader if ever in doubt.

### What to watch (Grafana + logs)
- fills round-tripping into the `fills` table and the OF-RECORD dashboard panels
- entry slippage vs the sim's marketable-limit assumption; stop-fill prices vs `min(stop, trade)` − 2 ticks
- `modify_stop` acknowledgement latency (trail correctness under rate limits)
- daily: `SELECT * FROM v_round_trips` vs the runner's log of intended trades

### Success criteria (two-week soak, per the B6 pattern)
- **Plumbing PASS:** zero unexplained position/fill mismatches; every trail modification acknowledged; flatten fires 15:55 every session; reconciliation of `fills` vs demo statements clean.
- **Model PASS:** live fill quality within the pessimistic model's assumptions (if live is *worse* than the model, all past research was optimistic — must know).
- **Strategy expectation (honesty):** per the holdout, expect roughly −$60/session in quiet weeks, with occasional large green days. Two weeks of demo P&L is **noise** and must not be read as validation — the 65-session aggregate (−$2,076) is the standing estimate.

### Explicitly out of scope / risks
- **This is not a promotion.** The strategy failed the factory's economics everywhere except expansion weeks; the lifecycle table has no `live` row for it, and the demo does not create one.
- The recent four green weeks are the seduction risk named in §2 — do not scale, do not flip `live_trading`, regardless of a good demo fortnight.
- The known fix-shaped hypothesis — a **pre-open volatility gate** (trade only when expansion conditions hold) — is the next research step if the demo plumbing passes. It must be built on dev data and validated once, not tuned on more holdout weeks.

---

## 4. Checklist for Sunday night / Monday morning
- [ ] Rotate the Databento API key (still outstanding) and update `.env`
- [ ] Set the Databento portal spending limit (still "No limit")
- [ ] `dry_run: false`, `live_trading: false` in `config/config.yaml`
- [ ] Run the contract resolver after 18:30 ET; confirm active contract (roll to MESZ6 approaching — Sep expiry ~Sep 18)
- [ ] Optional tonight (Globex reopens 18:00 ET Sun): start the runner to verify connectivity; entries only begin 08:00 ET Monday
- [ ] Grafana up; confirm the trade-success dashboard shows the demo fills as they arrive
