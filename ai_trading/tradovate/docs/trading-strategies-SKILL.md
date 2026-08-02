---
name: trading-strategies
description: Rule-based trading strategy playbook for signal generation and automation. Use this skill whenever implementing, backtesting, or automating discretionary price-action setups (pullbacks, trend continuation entries) in Pine Script or Python execution bots. Skill 1 covers the Two-Legged Pullback pattern for both long and short entries, including futures-specific adaptation rules.
---

# Trading Strategies Playbook

## Skill 1: Two-Legged Pullback

A trend-continuation setup. Enter in the direction of the prevailing trend after price makes exactly two corrective legs against it.

### Concept

- In an uptrend (series of HH/HL), a healthy pullback often forms two distinct down-legs (L1, then L2) before the trend resumes.
- In a downtrend (LH/LL), the mirror applies: two up-legs, then continuation down.
- The second leg completing without breaking trend structure is the trigger zone.

### BUY Rules (uptrend)

1. Confirm market is in an uptrend (higher highs, higher lows).
2. Wait for 2 small pullbacks — two distinct lower-low legs (L1, L2) within the pullback.
3. Entry: buy stop at the HIGH of the signal candle (the candle completing leg 2).
4. Stoploss: LOW of the signal candle.
5. Target 1 (T1): exit half position at 1:2 risk/reward.
6. Target 2 (T2): exit remaining at 1:4 risk/reward.

### SELL Rules (downtrend)

1. Confirm market is in a downtrend (lower highs, lower lows).
2. Wait for 2 small pullbacks — two distinct higher-high legs (L1, L2).
3. Entry: sell stop at the LOW of the signal candle.
4. Stoploss: HIGH of the signal candle.
5. T1: exit half at 1:2.
6. T2: exit remaining at 1:4.

### Risk Model

- R = |entry − stoploss| (signal candle range).
- Position sized so 1R = fixed % of account (suggest 0.5–1% for futures).
- After T1 fills, move stop to breakeven on the remaining half (optional but recommended; pairs with the quadrant trailing-stop tool).

---

## Futures Adaptability Assessment (Skill 1)

**Verdict: adaptable, with modifications.** The pattern logic is instrument-agnostic — swing structure, candle-anchored entries, and R-multiple exits translate directly. Issues to handle:

### What ports cleanly
- HH/HL/LH/LL swing detection (pivot-based, e.g. `ta.pivothigh`/`ta.pivotlow` or Python zigzag).
- Stop-order entry at signal-candle high/low → Tradovate stop order.
- Bracket exits (1:2 half, 1:4 remainder) → Tradovate OCO/bracket orders.

### What needs modification for futures (ES/NQ/CL etc.)
1. **Tick rounding**: entry, SL, and both targets must round to the instrument's tick size (ES 0.25, NQ 0.25, CL 0.01). A 1:2 target computed from a raw range will often be off-tick.
2. **Partial exits require ≥2 contracts**: "exit half" is impossible with 1 contract. With 1 contract, choose T1-only or T2-only, or trail instead.
3. **Signal candle range vs. tick value**: on NQ, a wide signal candle can mean a stop of 100+ points ($2,000+/contract). Add a max-risk filter that skips signals where candle range × tick value exceeds the per-trade risk budget.
4. **Session guards**: pattern quality degrades in overnight/low-volume sessions. Restrict to RTH or high-volume windows (consistent with the existing scalping bot's session logic).
5. **Slippage on stop entries**: stop orders on fast futures can fill several ticks worse. Backtest with realistic slippage (1–2 ticks ES, 2–4 NQ).
6. **Leg detection is subjective**: "two small pullbacks" needs a mechanical definition for automation — e.g., two consecutive pivot lows within the pullback where the second undercuts the first, while price holds above the prior major HL. This is the hardest part to codify and should be validated with walk-forward testing before live use.

### Recommended architecture
Same hybrid pattern as the existing projects: Pine Script v5 for visual confirmation/alerts, Python bot on the VPS talking directly to Tradovate REST/WebSocket for actual bracket placement and the breakeven/trailing logic after T1.

---

## Skill 2: Positional Trading Strategy (Consolidation Breakout)

A trend-continuation breakout setup confirmed by volume contraction/expansion. Card 7.2, "Price Action" category.

### Concept

- After a sustained move, price pauses in a tight consolidation range.
- Volume drying up during the consolidation signals sellers/buyers are exhausted, not reversing.
- A breakout candle that is large-bodied AND on expanded volume confirms trend continuation.

### BUY Rules (upmove)

1. Instrument in a clear upmove.
2. Consolidation forms (sideways range after the move).
3. Volume during consolidation should be LOW (contraction vs. prior bars).
4. Enter on breakout above the consolidation with a big candle and big volume.
5. Entry: at/above the breakout candle close or high.

### SELL Rules (downmove)

1. Instrument in a clear downmove.
2. Consolidation forms.
3. Volume during consolidation should be low.
4. Enter on breakdown below the range with a big candle and big volume.

### Risk Model (card doesn't specify — recommended defaults)

- Stoploss: opposite side of the consolidation range (or breakout candle low/high for tighter risk).
- Targets: measured move (range height projected from breakout) or reuse Skill 1's 1:2 / 1:4 R-multiple ladder for consistency across the playbook.

### Mechanical Definitions for Automation

- **Consolidation**: N consecutive bars (e.g. 8–20) whose total high-low range ≤ k × ATR(14), or Bollinger Band width in bottom quantile of lookback.
- **Low volume**: consolidation average volume < X% (e.g. 70%) of the 20-bar volume SMA preceding the range.
- **Big candle**: breakout bar body ≥ 1.5–2× ATR(14) or ≥ 2× average body of consolidation bars.
- **Big volume**: breakout bar volume ≥ 1.5–2× the 20-bar volume SMA.
- **Breakout**: close beyond range high/low (close-based is more robust than wick-based against fake-outs).

### Futures Adaptability Assessment (Skill 2)

**Verdict: adaptable, and arguably better suited to futures than Skill 1** — but with one important caveat.

What ports cleanly:
- Consolidation/range detection, ATR-relative candle sizing, and close-based breakout triggers are all mechanical and instrument-agnostic.
- Futures volume (ES/NQ/CL) is real exchange volume — more reliable than spot forex tick volume — so the volume-contraction/expansion filter works well.

Caveats for futures:
1. **Volume baselines are session-dependent**: futures volume has a strong intraday U-shape (open/close heavy, lunch light). "Low volume" must be measured against the same time-of-day baseline, not a flat 20-bar SMA, or every lunchtime range will falsely qualify. Use relative volume (RVOL vs. same-time-of-day average) for intraday timeframes.
2. **Contract roll**: volume migrates to the front month around roll week; a naive volume filter will misfire. Use continuous volume-adjusted data or guard the roll window.
3. **Breakout slippage**: same as Skill 1 — big-candle breakouts fill worse on stop/market entries; model 1–4 ticks.
4. **Timeframe fit**: this is a positional (swing) setup by design. On daily/4H futures charts it ports almost 1:1. Compressing it to scalping timeframes weakens the volume signal — keep it as the swing-tier strategy in the playbook, complementary to the intraday scalper.
5. **Bar-close confirmation**: since entry requires evaluating candle size + volume, this must trigger on bar close — which conveniently sidesteps Pine Script's intrabar limitation. This one CAN live mostly in Pine with webhook alerts; the Python/Tradovate bot is only needed for order management.

---

## Skill 3: 9 & 21 EMA Support/Resistance Strategy

Trend filter + horizontal level breakout. Card 7.1, "Price Action" category. Chart settings on card: EMA 21 (close), EMA 9 (close).

### Concept

- The 9/21 EMA pair defines trend bias: 9 above 21 = bullish, 9 below 21 = bearish.
- Within the trend, price often consolidates against a horizontal support/resistance level (a range or trendline squeeze).
- Trade the break of that level ONLY in the direction the EMAs agree with — the EMA filter kills counter-trend breakouts.

### BUY Rules

1. 9 EMA > 21 EMA (bullish alignment).
2. Enter when a candle breaks the resistance level (top of the consolidation zone).
3. Stoploss: below the consolidation zone / recent swing low (per card chart).
4. Target: next resistance zone / measured move (card shows prior-range projection).

### SELL Rules

1. 9 EMA < 21 EMA (bearish alignment).
2. Enter when a candle breaks the support level.
3. Stoploss: above the broken structure / recent swing high.
4. Target: next support zone.

### Mechanical Definitions for Automation

- **EMA filter**: `ta.ema(close, 9) > ta.ema(close, 21)` for longs (mirror for shorts). Optionally require price > both EMAs.
- **Resistance/support level**: highest high / lowest low of the last N bars (e.g. `ta.highest(high, 20)`), or pivot-based horizontal level with ≥2 touches.
- **Break**: close beyond the level (close-based, not wick-based).
- **Optional strength filters**: borrow Skill 2's big-candle + volume expansion checks — the cards are clearly designed to stack (7.1 EMA filter + 7.2 volume confirmation).

### Risk Model (card doesn't specify R:R — recommended defaults)

- R = entry − stop (zone-based stop).
- Reuse the playbook ladder: half at 1:2, remainder at 1:4, or trail the remainder along the 21 EMA (exit on close back below it) for trend rides.

### Futures Adaptability Assessment (Skill 3)

**Verdict: highly adaptable — the most automation-friendly of the three so far.**

What ports cleanly:
- EMA crossover state is trivially computable in Pine and Python, identical on any instrument.
- Close-based level breaks fit bar-close evaluation → clean Pine webhook alerts, same as Skill 2.
- This is essentially a stricter cousin of the existing scalping bot's EMA logic — the codebase already has 90% of this.

Caveats for futures:
1. **Timeframe sensitivity**: 9/21 EMA behavior differs wildly between 1-min NQ and daily ES. The EMA filter whipsaws badly in chop on low timeframes — add a minimum EMA separation filter (e.g. |EMA9 − EMA21| > 0.25 × ATR) so "alignment" means a real trend, not a coin flip.
2. **Level detection is the weak link**: horizontal S/R on futures is often better defined by prior session high/low, overnight high/low, or VWAP-adjacent levels than by a rolling N-bar extreme. For intraday futures, seed the level set with session levels — they're where the actual stops and liquidity sit.
3. **No stop/target on the card**: the entry rules alone are incomplete for automation; the defaults above must be locked before backtesting so results are reproducible.
4. **Stacking recommendation**: run Skill 3's EMA filter as a regime gate on top of Skill 1 and Skill 2 signals. In backtests, a shared trend filter typically improves all breakout/pullback variants more than tuning any single strategy.

---

## Skill 4: Pinbar Candlestick Reversal Strategy

Mean-reversion at horizontal zones, triggered by a rejection candle. Card 7.3, "Price Action" category. Unlike Skills 1–3 (trend continuation), this is a REVERSAL / range strategy.

### Concept

- Mark a horizontal support or resistance zone (multiple prior touches — the card charts show clear range boundaries).
- Wait for price to enter the zone and print a pinbar: a candle with a long rejection wick and small body, showing the level held.
- The pinbar must CLOSE back on the favorable side of the zone — the close is the confirmation, not the wick.

### BUY Rules

1. Create/identify a support zone.
2. Wait for a pinbar (hammer) candle to trade into the zone and close ABOVE it.
3. Entry: on/after the pinbar close (card circles the hammer at support).
4. Target: opposite side of the range (resistance zone), per card chart.

### SELL Rules

1. Create/identify a resistance zone.
2. Wait for a pinbar (inverted hammer / shooting star) to trade into the zone and close BELOW it.
3. Entry: on/after the pinbar close.
4. Target: opposite side of the range (support zone).

### Risk Model (card doesn't specify — recommended defaults)

- Stoploss: beyond the pinbar wick extreme (a tick/few ticks past the rejection low/high). If the wick is taken out, the rejection thesis is dead.
- Target: opposite range boundary (per card), or 1:2 minimum if the range is wide; skip signals where range width < 2× pinbar risk.

### Mechanical Definitions for Automation

- **Pinbar (bullish/hammer)**: lower wick ≥ 2× body; body in upper third of candle range; close > open preferred. Mirror for bearish.
- **Zone touch**: pinbar low penetrates the zone (zone = level ± 0.25–0.5 × ATR band, not a single price).
- **Close confirmation**: candle close above zone top (longs) / below zone bottom (shorts).
- **Zone construction**: pivot highs/lows with ≥2 touches within tolerance, or prior session high/low/close for intraday futures.
- **Optional regime filter**: only take these when Skill 3's EMAs are FLAT or when trading a defined range — a pinbar against a strong EMA trend is a low-quality countertrend fade.

### Futures Adaptability Assessment (Skill 4)

**Verdict: adaptable, but the highest-risk of the four to automate.** Reversal fades are less forgiving than continuation setups.

What ports cleanly:
- Pinbar geometry (wick/body ratios) is purely mechanical — trivial in Pine and Python.
- Close-based confirmation fits bar-close evaluation → clean webhook alerts.
- Wick-extreme stops map directly to Tradovate stop orders.

Caveats for futures:
1. **Stop-run behavior**: index futures routinely sweep obvious wick lows by a few ticks before reversing. Place the stop 2–4 ticks beyond the wick (ES) rather than exactly at it, and size for that wider stop.
2. **Pinbar quality is timeframe-dependent**: on 1-min charts pinbars are noise; this setup performs best on 15-min+ for intraday futures or 4H/daily for swing. Don't feed it to the scalper timeframe.
3. **Zone subjectivity**: like Skill 3, the zone is the weak link. For futures, anchor zones to session levels (prior day high/low, overnight range, weekly open) — these get respected far more than arbitrary pivot clusters.
4. **Countertrend danger**: automated pinbar fades in a trending futures session bleed money. The regime filter above (only in ranges / EMA-flat conditions) is effectively mandatory, not optional, before this goes live.
5. **Complementary role**: Skills 1–3 are trend strategies; Skill 4 is the range strategy. Together they cover both regimes — route signals by a regime classifier (EMA separation / ADX) so only the matching strategy is active.

---

## Skill 5: Martingale System (1-Min SMA Scalp)

Mean-reversion scalp with position-doubling on losses. Card 5.6, "Scalping" category. Chart settings: SMA 5 and SMA 14 (card overlay shows EMA labels; text specifies SMA — use SMA per the rules).

### Concept

- On the 1-minute chart, price stretched away from SMA14 tends to snap back to it.
- Enter counter to the recent push when a reversal candle prints; target is simply the SMA14 line.
- If the trade fails, re-enter at the next signal with doubled size (1x → 2x → 4x), so one winning snap-back at SMA14 recovers all prior losses.

### BUY Rules (as written on card)

1. Timeframe: 1 minute. Indicators: SMA5 and SMA14.
2. SMA5 < SMA14 (bearish crossover — price extended below the mean).
3. Wait for a candle to turn green; buy at the high of that candle.
4. If trade 1 fails: take the next entry candle with 2x quantity.
5. If trade 2 fails: next signal candle with 4x quantity.
6. Target: SMA14. Exit ALL open trades the moment price touches SMA14.
7. Per-trade stoploss: low of the entry candle (per card chart).

### SELL Rules

Mirror: SMA5 > SMA14, wait for a red candle, sell at its low, double on failures (2x, 4x), exit everything at SMA14 touch.

### Mechanical Definitions for Automation

- **Crossover state**: `ta.sma(close,5) < ta.sma(close,14)` for buy setups.
- **Signal candle**: first green candle (close > open) after state is true; buy stop at its high.
- **Sequence state machine**: track attempt number (1, 2, 3) and cumulative position; hard-reset the sequence on SMA14 touch OR after attempt 3 fails.
- **Target order**: exit at SMA14 value — note SMA14 moves each bar, so the target must be updated bar-by-bar (this is genuinely dynamic order management, a Python/Tradovate job, not a static bracket).

### Futures Adaptability Assessment (Skill 5)

**Verdict: mechanically portable, but I don't recommend automating the martingale sizing on futures as written.** This is the one card in the deck where the honest answer is "adapt the signal, discard the sizing."

The math on leveraged futures:
- 1x → 2x → 4x means a 3-loss sequence carries 7x base risk. On MNQ with a modest 10-point stop, that's ~$140/sequence at 1 micro base — survivable. On NQ full-size, the same sequence risks ~$1,400+, and a fast trending 1-min move (exactly the condition that produces consecutive losses) can blow through several sequences in one session.
- Martingale's failure mode is fat-tailed: it wins small frequently, then loses catastrophically in the trend it keeps fading. On margined futures, drawdowns can also trigger margin calls mid-sequence, forcing liquidation at maximum size at the worst price.
- The card at least caps at 4x with a per-trade stoploss — better than pure martingale — but the risk profile is still inverted (biggest size on the weakest thesis).

What IS worth keeping:
1. **The signal itself is fine**: SMA5/SMA14 stretch + reversal candle + SMA14 magnet target is a legitimate 1-min mean-reversion scalp, very close to the existing scalping bot's logic. Backtest it at FLAT sizing first — if it has no edge at 1x, martingale only changes how fast it loses.
2. **Safer sizing alternatives**: fixed-fractional (same risk every attempt, max 2–3 attempts), or anti-martingale (increase size after wins, not losses).
3. **If a scaled-sequence version is ever tested**: cap the sequence at 2x total, hard daily-loss limit at the bot level, micros only (MNQ/MES), and a trend circuit-breaker (no re-entries when ADX or EMA-separation says the market is trending away from the mean).
4. **Dynamic target note**: exiting at a moving SMA14 requires live order modification each bar — this strategy is Python/Tradovate-bot territory end to end; Pine webhooks can't manage it.

Playbook role: Skill 5's entry logic can serve as the mean-reversion scalp module alongside Skill 4 (range reversal), gated by the same regime classifier. The martingale ladder should stay on the card, not in the bot.

---

## Skill 6: Moving Average Scalping Strategy (EMA7 Snap-Back)

Mean-reversion scalp to the EMA7 on the 5-minute chart. Card 5.5, "Scalping" category. Chart settings: EMA(9, close, 0, SMA, 5) shown on card charts; rules text specifies EMA7 — use EMA7 per the rules.

### Concept

- On the 5-min chart, when an entire candle detaches fully below (or above) the EMA7 — no touch — price is short-term overextended.
- Trade the snap-back: enter on a break of that detached candle back toward the EMA, target the EMA line itself.
- The "keep updating the signal candle" rule makes this a trailing entry: each new, lower detached candle replaces the previous trigger level, so you only get filled when momentum actually turns.

### BUY Rules

1. Timeframe: 5 minutes. Indicator: EMA7.
2. Candle fully below EMA7 — high does not touch the EMA.
3. Buy stop at the high of that candle.
4. If the market keeps going down, keep updating the signal candle (move the buy stop to the newest qualifying candle's high).
5. Stoploss: swing low.
6. Target: the moving average (EMA7).

### SELL Rules

Mirror: candle fully above EMA7 (low doesn't touch), sell stop at its low, trail the trigger down the newest qualifying candle if price keeps rising, stop at swing high, target EMA7.

### Mechanical Definitions for Automation

- **Detached candle (long)**: `high < ema7` on bar close.
- **Trailing trigger**: on each new detached candle, cancel/replace the buy stop at the new high — native cancel-replace on Tradovate.
- **Swing low stop**: lowest low of the last N bars (e.g. 5) at fill time, or the low of the detachment sequence.
- **Dynamic target**: EMA7 recomputed per bar; exit order must be modified each bar (same live-management requirement as Skill 5).
- **Optional quality filter**: require detachment depth ≥ 0.5 × ATR(14) below the EMA so marginal 1-tick detachments don't trigger.

### Futures Adaptability Assessment (Skill 6)

**Verdict: well suited to futures scalping — this is Skill 5's signal concept with sane risk mechanics, and the better candidate of the two scalping cards.**

What ports cleanly:
- Detachment test and trailing stop-entry are exact, bar-close-evaluable rules.
- Flat sizing with a structural (swing) stop — no martingale ladder — makes the risk profile conventional.
- The trailing signal-candle mechanism is genuinely good design: in a strong 5-min trend the trigger keeps stepping away, so the bot never catches the falling knife at a fixed level.

Caveats for futures:
1. **Small reward per trade**: the target (EMA7) is often only a handful of points away, so commissions + slippage eat a large fraction of edge. Compute expected move-to-EMA vs. round-trip cost per instrument; NQ/MNQ tick economics usually survive this, ES less so on shallow detachments — the ATR depth filter above doubles as a cost filter.
2. **Asymmetric R:R**: swing-low stop vs. EMA target is frequently worse than 1:1. That's acceptable only if hit rate is high — this must be validated in backtest, not assumed.
3. **Order churn**: the cancel-replace trailing entry generates many order modifications; fine on Tradovate's API but build in rate-limit awareness and idempotent order IDs.
4. **Trend-day guard**: on strong trend days price can stay detached and grind — the trailing entry protects entries, but once filled, a snap-back target may never come before the swing stop. A time-stop (exit if target untouched after N bars) is a worthwhile addition.
5. **Fit with existing bot**: this is architecturally the closest card yet to the current scalping bot (EMA-based, 5-min, webhook-friendly signal, Python-managed dynamic target). It could likely be implemented as a mode of the existing bot rather than a new system.

Playbook note: Skills 5 and 6 are both EMA/SMA snap-back scalps. Skill 6 supersedes Skill 5 for automation — same thesis, cleaner mechanics, no martingale. If only one goes into the bot, it's this one.

---

## Skill 7: Scalping 1-Minute Consolidation Breakouts

Micro-flag continuation scalp on the 1-minute chart. Card 5.4, "Scalping" category.

### Concept

- In a moving 1-min market, a tight cluster of ~4 small candles (a micro-consolidation / flag) is a pause, not a reversal.
- Trade the break of that cluster in the direction of the prevailing move.
- This is Skill 2's consolidation-breakout logic compressed to the 1-min scalping timeframe with a fixed-size cluster instead of a volume filter.

### BUY Rules

1. Timeframe: 1 minute.
2. Market going up.
3. 4-candle pullback of SMALL candles (tight micro-range).
4. Enter at the high (buy stop above the cluster high).
5. Stoploss: below the consolidation range.

### SELL Rules

Mirror: market going down, 4 small-candle pullback, sell stop at the cluster low, stop above the consolidation range.

### Risk Model (card doesn't specify target — recommended defaults)

- R = cluster height + entry offset.
- Target: 1:1 to 1:2 for a 1-min scalp, or trail with the quadrant tool once 1R is reached. Skip signals where the cluster is so tight that R < spread + commissions × 2.

### Mechanical Definitions for Automation

- **"Market going up"**: needs a mechanical trend proxy — e.g. EMA9 > EMA21 on the 1-min (borrow Skill 3's filter), or price above VWAP, or N of last M closes rising.
- **Small candles**: each of the 4 candles has range ≤ k × ATR(14) (e.g. k = 0.6), or cluster total range ≤ 1 × ATR.
- **Cluster bounds**: highest high / lowest low of the 4 qualifying bars.
- **Entry**: buy stop 1 tick above cluster high; cancel if a candle closes outside the cluster in the wrong direction first.
- **Flexible count**: consider accepting 3–6 small candles rather than exactly 4 — a hardcoded 4 is curve-fit; the concept is "brief tight pause."

### Futures Adaptability Assessment (Skill 7)

**Verdict: adaptable, and a natural fit for the existing scalper — but 1-min execution demands the Python/Tradovate path, not webhooks.**

What ports cleanly:
- Cluster detection (ATR-relative candle sizes, rolling high/low) is fully mechanical.
- Stop-entry + range-based stop maps directly to a Tradovate bracket.
- Pairs naturally with the quadrant trailing-stop tool for exit management since the card gives no target.

Caveats for futures:
1. **Latency matters here more than any other card**: 1-min breakout fills degrade fast. The TradingView-webhook→bot path adds seconds; on this setup that's often the whole edge. Signal detection should run in the Python bot on live WebSocket data, with Pine used only as a visual overlay — exactly the architecture already established for the SL tool.
2. **False-break rate is high on 1-min index futures**: micro-clusters get swept both ways around news, opens, and thin lunch tape. Mandatory guards: session window (e.g. first 2–3 RTH hours), economic-calendar blackout, and a max-spread/volatility sanity check.
3. **The trend filter is the edge**: without a strict "market going up" definition this degenerates into trading every 1-min chop cluster. The EMA-separation or VWAP-side filter should be tight enough that the bot sits out ranging days entirely.
4. **Cost sensitivity**: like Skill 6, per-trade profit is small; MNQ/NQ economics work, ES marginal. Enforce the minimum-R filter above.
5. **Playbook overlap**: Skill 7 (1-min flag break) and Skill 6 (5-min EMA snap-back) are complementary scalps — one continuation, one mean-reversion — and can share the same bot infrastructure, session guards, and risk manager with different signal modules.

---

## Skill 8: Scalp Trading with RSI and VWAP

Mean-reversion scalp combining an oscillator extreme with the session's institutional anchor. Card 5.3, "Scalping" category. Chart settings: VWAP (Session, hlc3, bands 1/2/3) and RSI(14, close, SMA 14 smoothing).

### Concept

- VWAP is the session's volume-weighted fair value; price bouncing off it in the trend direction is a high-quality pullback location.
- RSI at an extreme (<30 long / >70 short) times WHEN the bounce is stretched enough to take.
- Both conditions together = price at a meaningful level AND momentum washed out.

### BUY Rules

1. Timeframe: 1 minute.
2. RSI(14) < 30.
3. Price taking support at VWAP (pullback holds at/near the VWAP line — card shows the bounce candle with stop just below).
4. Exit when RSI > 70.
5. Stoploss: below the VWAP-hold candle / just under VWAP (per card chart).

### SELL Rules

Mirror: RSI > 70, price rejecting at VWAP resistance, exit when RSI < 30, stop above the rejection candle / just over VWAP.

### Mechanical Definitions for Automation

- **VWAP**: session-anchored, hlc3 source, reset at RTH open. Bands at ±1/2/3 stdev (card overlay) can define "near": price within 0.25 × ATR or inside the ±1 band around VWAP.
- **Support hold**: candle low touches/penetrates the VWAP zone but closes back above it (same close-back-through confirmation as Skill 4's pinbar).
- **Entry**: on the confirming candle close, or stop above its high for momentum confirmation.
- **RSI exit**: evaluated per bar close; exit market on first close with RSI > 70 (long).
- **Sequencing note**: the RSI extreme and the VWAP touch rarely land on the same bar. Implement as a state machine: RSI < 30 arms the setup (valid for N bars), VWAP hold then triggers it.

### Futures Adaptability Assessment (Skill 8)

**Verdict: highly adaptable — VWAP is arguably MORE meaningful on index futures than anywhere else, since it's the benchmark institutional desks actually execute against.**

What ports cleanly:
- Session VWAP, RSI, and band math are standard in Pine and Python (careful: anchor VWAP to RTH open for ES/NQ, not the continuous session, or the level loses its institutional meaning — decide RTH vs. ETH anchoring explicitly and keep it consistent between backtest and live).
- The card already matches the existing scalping bot's indicator set (RSI is in the current EMA/RSI/MACD logic) — this is a recombination, not new infrastructure.

Caveats for futures:
1. **The RSI exit is the weak link**: "exit when RSI > 70" has no price-based protection and can hold through a failed bounce that never reaches 70. Keep the card's hard stoploss, and add a time-stop or a fallback take-profit (e.g. VWAP +1 band) so trades don't linger. In backtests, compare RSI-exit vs. band-target exit — the band target is usually more consistent on 1-min index futures.
2. **RSI(14) on 1-min rarely prints <30 in quiet tape**: signal frequency will be low outside volatile sessions. That's fine (selectivity is good) but set expectations; consider RSI(7) as a tested variant if frequency is too low — as a variant, not a silent change.
3. **Direction filter**: the card's long setup (RSI oversold + VWAP support) implicitly assumes an up day. Make it explicit: longs only above VWAP-open relationship or with EMA bias agreeing, shorts mirror. Fading VWAP breaks on trend days is the classic way this setup loses.
4. **First 15–30 min caution**: VWAP is statistically unstable right after the open (few data points); bounces off it then are noise. Start the strategy window after VWAP has matured.
5. **Playbook fit**: this completes a clean scalping trio — Skill 7 (continuation flag break), Skill 6 (EMA snap-back), Skill 8 (VWAP + RSI location scalp). All three share the bot chassis; Skill 8's VWAP module also strengthens Skill 7's "market going up" filter for free.

---

## Skill 9: Trading the Bollinger Bands (Fake-Move Reversal)

Trend-resumption entry after a "fake" counter-move to the opposite band. Card 1.1, "Strategies Based On Swings" category.

⚠️ **Card quality flags (important):**
1. The rules text contains a printing error: "difference between (lower Bollinger Band and mean) is greater than difference between (lower Bollinger Band and mean)" — the same quantity twice. The comparison as printed is meaningless and, with standard Bollinger Bands, band-to-mean distances are symmetric by construction anyway.
2. The chart side of this card shows SMA(14) + Williams %R(14) with "pullback from -50" annotations — a different indicator set than the Bollinger text. The graphic appears to belong to a Williams %R pullback strategy; text and chart don't match.

The rules below record the card as written, then the most sensible mechanical interpretation. Treat this skill as PROVISIONAL until the intended logic is confirmed (e.g. against the ZebraLearn book/source).

### Concept (as intended, best reading)

- In an uptrend, price rides near the upper band.
- A sudden sharp fall drops price to/near the LOWER band — but the fall lacks follow-through ("probably fake").
- Buy the first green candle (or its high) for a resumption move back toward the upper band.

### BUY Rules (card text, verbatim intent)

1. Price in uptrend, near the upper Bollinger Band.
2. Sudden fall; price becomes near the lower Bollinger Band.
3. [Garbled condition — see flag #1.]
4. Fall judged fake → BUY at the green candle or high of the green candle.
5. Stoploss: swing low.
6. Target: upper Bollinger Band.

### SELL Rules

Mirror: downtrend near lower band, sudden rise to upper band, rise judged fake, sell at the red candle or its low, stop at swing high, target lower band.

### Proposed Mechanical Interpretation (for automation)

The tradable idea is "sharp counter-move into the far band WITHOUT genuine trend reversal." Candidate mechanical tests for "fake":
- **No close beyond the band**: price tags/nears the lower band intrabar but doesn't close below it (band held).
- **Trend context intact**: mid-band (20 SMA) still rising, and/or EMA9 > EMA21 regime (Skill 3's gate) still true.
- **Speed asymmetry**: the fall took ≤ M bars (sudden), vs. the preceding rise of ≥ N bars — a fast shallow-participation drop, not distribution.
- **Trigger**: first close > open candle after the band touch; buy stop at its high (consistent with the deck's other close-based entries).
- Backtest these variants separately; adopt whichever the data supports rather than guessing the author's intent.

### Futures Adaptability Assessment (Skill 9)

**Verdict: the underlying pattern (V-reversal continuation in a trend) is tradable on futures, but this card is NOT automation-ready as printed — the defining condition is corrupted. Rank it lowest priority until the logic is reconstructed and validated.**

Additional futures notes:
1. Bollinger Bands themselves port fine (BB(20,2) is standard in Pine/pandas); band-touch and band-close tests are mechanical.
2. "Sudden fall in an uptrend" on index futures is frequently news-driven — the exact case where mean-reversion buying gets run over. An economic-calendar blackout (already required for Skills 7–8) is mandatory here too.
3. The "buy the first green candle" trigger after a sharp fall has wide stop distance (swing low of the fall) — check that R vs. the upper-band target still clears 1:1.5 after slippage; sharp-fall bars fill poorly.
4. Overlap note: mechanically this converges toward Skill 8 (buy washed-out dip at a statistical level in an uptrend). If reconstruction doesn't produce a distinct edge, fold it into Skill 8's module rather than maintaining a ninth strategy.

---

## Skill 10: Trading Breakouts with BB and Width (Squeeze Breakout)

Volatility-contraction breakout using Bollinger Band Width as the squeeze detector. Card 1.6, "Strategies Based On Swings" category. Chart settings: BB(20, SMA, close, 2, 0) and BBW(20, close, 2).

### Concept

- Bollinger Band Width near zero and flat = volatility squeeze; the market is coiling.
- When BBW breaks out of its flat base AND a candle closes outside a band, volatility is expanding in that direction — ride the expansion.
- The middle line (20 SMA) serves as both initial stop and trailing stop, keeping you in for the whole expansion leg (card's target circles are simply where price finally re-crosses the mid-line).

### BUY Rules

1. Timeframe: 30 minutes. Style: swing trading.
2. BB width close to 0 and flat (tight, quiet base — card boxes the squeeze region on both price and BBW panes).
3. Wait for BB width to break (BBW spikes out of its flat range).
4. AND the candle closes above the upper Bollinger Band.
5. Take the breakout trade.
6. SL and TSL: middle line of BB (20 SMA) — trail it as the trend runs.

### SELL Rules

Mirror: BBW near 0 and flat, BBW breaks out, candle closes below the lower band, short; SL/TSL at the BB middle line.

### Mechanical Definitions for Automation

- **BBW**: (upperBB − lowerBB) / middleBB (TradingView's BBW). "Close to 0 and flat": BBW below the Xth percentile (e.g. 20th) of its last 100–200 bars AND BBW range over last N bars ≤ small epsilon — percentile beats an absolute level since BBW scale varies by instrument.
- **Width break**: BBW > its highest value of the prior N bars (e.g. 20), or BBW > squeeze-percentile × k.
- **Entry trigger**: bar close beyond the band while width-break condition is true (both on the same closed bar, or width-break within the last 1–3 bars).
- **Trailing stop**: exit on close beyond the 20 SMA against the position (close-based, consistent with the playbook), evaluated each bar.
- This is the volatility-regime twin of Skill 2: Skill 2 detects the pause with volume, Skill 10 detects it with band width. Same thesis, different sensor.

### Futures Adaptability Assessment (Skill 10)

**Verdict: highly adaptable — squeeze breakouts are a proven futures pattern, and this card's rules are unusually complete (timeframe, entry, stop AND trailing logic all specified).**

What ports cleanly:
- BBW percentile squeeze detection is standard and robust across ES/NQ/CL.
- Bar-close entry + close-based SMA trail = fully bar-close evaluable → Pine webhook alerts work, with the Python bot handling the trailing-stop order updates each 30-min bar (slow cadence, no latency pressure — the easiest live-management profile in the whole playbook).
- The 20 SMA trailing stop is structurally similar to the quadrant trailing SL tool's job; the bot's existing trailing infrastructure covers it.

Caveats for futures:
1. **Initial risk can be wide**: at breakout, entry (outside band) to the middle line is by definition ≥ 2 standard deviations. On a 30-min NQ chart that can be a large dollar risk — size positions from measured stop distance, and skip signals where 2σ exceeds the per-trade risk budget.
2. **Squeeze breakouts fail ~half the time by head-fake**: the classic failure is a one-bar poke outside the band that snaps back. The "BBW must also break" condition is precisely the filter that mitigates this — do not weaken it in implementation; require both legs.
3. **Session artifacts on 30-min futures**: overnight bars compress BBW artificially. Compute the squeeze on RTH-only data or accept that some squeezes are just the overnight lull (same session-baseline issue as Skill 2's volume).
4. **News-driven expansions**: on futures, the squeeze often resolves ON a scheduled release (FOMC, CPI). Unlike the 1-min scalps, this 30-min swing setup can legitimately trade those expansions — but slippage on the entry bar will be worse; model it.
5. **Playbook fit**: strongest swing-tier candidate alongside Skill 2. The two can share one "compression detector" module with two sensors (volume contraction, BBW percentile) and one breakout executor.

---

## Skill 11: Sectoral Analysis (Sector-vs-Constituent Confirmation)

Relative-strength / correlation approach: use the sector index as context for trading its constituents. Card 4.3, category shown as "Sectoral Analysis: A powerful way to trade."

⚠️ **INCOMPLETE — rules side not yet captured.** Only the chart face of this card was photographed. The BUY/SELL bullet rules are missing, so the entry/stop/target specifics below are inferred from the chart, not recorded from the card. Re-shoot the text side to finalize.

### What the chart shows

- A candlestick instrument plotted with the CNXFMCG (NSE FMCG sector index) overlaid as a line.
- The circled region marks the point where the sector index turns up sharply while the underlying stock is still falling / bottoming — i.e. the sector leads, the constituent follows.
- After the circled divergence, the stock reverses upward alongside the sector; later, both roll over together.

### Concept (inferred — pending rules text)

- A single stock's move is largely explained by its sector. Trading a constituent against its sector's direction is fighting the dominant factor.
- Signals: (a) confirmation — take long setups in a stock only when its sector index is also strong; (b) divergence/lead — when the sector turns before the constituent, anticipate the constituent following.

### Futures Adaptability Assessment (Skill 11) — preliminary

**Verdict: conceptually transferable, but this is the least directly portable card in the deck, and it works differently on futures than on Indian equities.**

1. **The original use case is stock-picking**: sector index → pick constituent stocks. Futures traders don't have "constituents" in the same sense — you trade the index itself (ES, NQ, YM, RTY), so there's no stock to select.
2. **The transferable version is inter-market/breadth confirmation**, which IS valuable on futures:
   - Cross-index confirmation: ES vs. NQ vs. RTY vs. YM. When one index diverges (e.g. NQ making highs while RTY fails), it's a well-known caution signal for index longs.
   - Sector ETF breadth (XLK, XLF, XLE) as a regime input for ES/NQ direction — the closest true analogue to this card.
   - Related-market context: DXY, /ZN yields, /CL for risk-on/risk-off tone.
3. **Implementation shape**: this is a FILTER/GATE, not a standalone entry strategy — same architectural role as Skill 3's EMA regime gate. Layer it on Skills 1, 2, 7, 8, 10 rather than building a separate bot.
4. **Data plumbing**: requires multi-symbol streaming (correlated instrument alongside the traded one) in the Python bot. Tradovate can stream several contracts; ETF/breadth data would need a second source. Worth scoping before committing — this is the highest data-infrastructure cost of any card so far, for a filter whose incremental edge should be measured before it's built.
5. **Backtest first, cheaply**: test a simple version (e.g. "only take ES longs when NQ is also above its VWAP/EMA") on existing data before adding a real-time multi-feed dependency.

---

## Skill 12: Supertrend with RSI

Trend-following entries from a Supertrend flip, confirmed by RSI momentum. Card 4.2. Chart settings: Supertrend(10, 3) and RSI(14, close, SMA 14, 2).

⚠️ **INCOMPLETE — rules side not yet captured.** Only the chart face was photographed (same as Skill 11). Rules below are read off the chart annotations, not the card's BUY/SELL text. Re-shoot the text side to confirm thresholds.

### What the chart shows

**BUY panel:** Supertrend flips from red to green; entry is circled on the first candle in the green regime. Stoploss sits on the Supertrend line below price. RSI is circled crossing UP through the upper dashed threshold at the same time. Target is marked far up the trend, near where Supertrend eventually flips back.

**SELL panel:** mirror — Supertrend flips green→red, entry circled at the flip candle, stoploss on the Supertrend line above price, RSI circled crossing DOWN through the lower dashed threshold, target where Supertrend flips back green.

### Inferred Rules (pending text confirmation)

**BUY**
1. Supertrend(10,3) flips bullish (price closes above the Supertrend line; band turns green).
2. RSI(14) confirms by crossing above its upper threshold (dashed band — likely 60, possibly 50; confirm from text).
3. Entry at the flip candle / its close.
4. Stoploss: the Supertrend line itself.
5. Target/exit: Supertrend flip back to bearish (i.e. trail the Supertrend line until it flips).

**SELL** — mirror in every respect.

### Mechanical Definitions for Automation

- **Supertrend(10,3)**: ATR period 10, multiplier 3 — standard, available in Pine (`ta.supertrend`) and easily implemented in Python/pandas.
- **Flip detection**: direction change on bar close (`dir != dir[1]`).
- **RSI gate**: `ta.rsi(close,14)` crossing the threshold; the card's "SMA 14 2" suggests an RSI-smoothing SMA with bands — reproduce the exact overlay once the text confirms it.
- **Exit**: on Supertrend flip against the position, evaluated at bar close.
- **Note**: stop and trailing stop are the same object here (the Supertrend line), which moves each bar — same live order-modification requirement as Skills 5, 6 and 10.

### Futures Adaptability Assessment (Skill 12)

**Verdict: very well suited to futures — Supertrend is ATR-based, so it self-scales to each instrument's volatility, and this is among the cleanest automations in the deck.**

What ports cleanly:
- Everything is bar-close evaluable: flip detection, RSI threshold, trailing exit. Pine webhook alerts work; the Python bot updates the Supertrend stop each bar.
- ATR-based stop distance auto-adjusts between ES/NQ/CL rather than needing per-instrument tuning — a real advantage over the fixed-level cards.
- Reuses RSI already in the existing bot's indicator set.

Caveats for futures:
1. **Supertrend whipsaws in chop** — this is its defining weakness. On a ranging 5-min futures session, (10,3) can flip repeatedly and bleed. The RSI confirmation is what's supposed to filter that; verify in backtest that RSI actually suppresses the whipsaw flips rather than just delaying entries. If it doesn't, add an ADX or EMA-separation regime gate (Skill 3's filter) on top.
2. **Parameter sensitivity**: (10,3) is the common default but is timeframe-dependent. Test (10,3) and (7,3)/(10,2) variants per instrument and timeframe rather than assuming the card's numbers transfer.
3. **Wide initial risk on volatile opens**: at a flip, entry-to-Supertrend distance is ~3×ATR. On NQ that can exceed the per-trade budget — apply the same max-risk skip filter used in Skills 1 and 10.
4. **No fixed profit target**: the card exits only on the opposite flip, so this is a "let it run" trend system with a low win rate and large winners. That's fine, but it needs the matching mindset and equity-curve expectations — don't evaluate it on win rate.
5. **Playbook fit**: this is the cleanest pure trend-follower in the deck and the natural swing-tier companion to Skill 10 (squeeze breakout entry → Supertrend trail). Consider using Skill 10 for entry timing and Skill 12's Supertrend as the exit manager for the same trade.

---

## Skill 13: Moving with Macro Trends (Pivot Point Levels)

Directional trading off classic floor-trader pivot levels. Card 4.1. Chart settings: Pivots — Traditional, Auto timeframe, 15 pivots back.

⚠️ **INCOMPLETE — rules side not yet captured.** Third card in a row with only the chart face. Rules below are read off the chart annotations. Re-shoot the text side to confirm the entry trigger and the exact stop placement.

### What the chart shows

**BUY panel:** Price works up through the pivot (P). Entry is marked just above P, with Stoploss immediately below the entry (below P / the entry candle's low). Target 1 is at R1; Target 2 is at the next session's R1/R2 region higher up. Price runs from P through R1 and beyond.

**SELL panel:** Price rallies into R1 and fails. Entry is marked below the rejection candle, Stoploss above at R1. Target 1 is at S1, Target 2 at S2. Price breaks down through P, S1, toward S2.

### Inferred Rules (pending text confirmation)

**BUY**
1. Plot Traditional pivots (P, R1, R2, S1, S2) for the session.
2. Price reclaims/holds above the pivot (P) — bullish bias for the session.
3. Entry: on the break/hold above P.
4. Stoploss: just below P (or below the entry candle's low).
5. Target 1: R1. Target 2: R2.

**SELL**
1. Price rejects at R1 (or loses P).
2. Entry: below the rejection candle / on the break below P.
3. Stoploss: above R1.
4. Target 1: S1. Target 2: S2.

Note the deck's recurring two-target structure (cf. Skill 1's 1:2 / 1:4) — here the targets are structural levels rather than R-multiples.

### Mechanical Definitions for Automation

- **Pivot math (Traditional)**: P = (H + L + C)/3 of the prior session; R1 = 2P − L; S1 = 2P − H; R2 = P + (H − L); S2 = P − (H − L). Fully deterministic — computed once per session, no ambiguity. This is the most objectively defined level set in the entire playbook.
- **Session definition is the key input**: for futures, decide whether the "prior session" is RTH-only or the full 23-hour ETH session. The two produce materially different pivot levels. Pick one, and keep backtest and live identical.
- **Bias rule**: `close > P` = long bias, `close < P` = short bias, evaluated at bar close.
- **Entry trigger needs the text side**: "break above P" vs. "retest and hold above P" are different systems with different fill and win-rate profiles. Flag as unresolved.
- **Targets**: static price levels for the whole session → simple bracket orders, no dynamic modification needed.

### Futures Adaptability Assessment (Skill 13)

**Verdict: excellent futures fit — arguably the most natural of any card in the deck. Pivot points originated on the futures floor.**

What ports cleanly:
- Levels are computed from prior-session OHLC, deterministic, and known before the session starts — the bot can precompute the whole level set at the open with zero indicator lag.
- Static targets and stops = plain bracket orders on Tradovate. No live modification, no latency pressure. Operationally the simplest card here.
- Widely watched on ES/NQ, which is the actual source of the edge: these levels attract real resting orders, so reactions at them are self-reinforcing rather than arbitrary.

Caveats for futures:
1. **RTH vs. ETH pivots is the single biggest implementation decision** — it changes every level. Most futures traders use RTH-derived pivots; test both.
2. **Chop around P**: price oscillating across the pivot generates repeated false bias flips. Require a buffer (e.g. close beyond P by ≥ 0.25 × ATR) or a confirmation bar before flipping bias.
3. **Trend-day vs. range-day dependency**: on range days price reverts between S1 and R1 (favoring the fade version); on trend days it runs through R1/R2 (favoring the breakout version). The card's BUY panel is a breakout and its SELL panel is a rejection fade — arguably two different strategies on one card. The missing text may resolve this; if not, treat them as separate modules with a regime gate.
4. **Level-cluster confluence**: pivots gain reliability when they coincide with prior-day high/low, VWAP (Skill 8), or overnight extremes. A confluence scorer combining these is a straightforward and probably worthwhile enhancement.
5. **Playbook fit**: this supplies the objective, mechanical level set that Skills 3 and 4 both needed and left vague ("create a support zone"). Best move may be to implement pivots once as a shared levels service, then let Skill 3 (EMA + level break), Skill 4 (pinbar at level) and Skill 13 all consume it.

---

## Skill 14: Gann Fan

Diagonal support/resistance from angled fan lines drawn off a major swing point. Card 3.7. Chart shows a Gann fan (1×1, 1×2, 1×3, 1×4, 1×8 and 2×1, 3×1, 4×1, 8×1) plus a linear regression line on the BUY panel, and a fan with moving averages on the SELL panel.

⚠️ **INCOMPLETE — rules side not yet captured.** Chart face only, fourth in a row. Rules below are inferred from the annotations.

### What the chart shows

**BUY panel:** A fan is anchored at a major swing low. Price rises along the steeper angles, then pulls back and the arrow marks "Taking support" where price lands on the 1×4 / 1×8 fan line and resumes upward. A linear regression line is drawn along the advance for comparison.

**SELL panel:** A fan is anchored at a major swing high in a downtrend. Price declines beneath the fan lines; "Sell" is circled where a rally fails at a fan line and rolls over. Moving averages are overlaid as secondary confirmation.

### Inferred Rules (pending text confirmation)

**BUY**
1. Anchor the Gann fan at a significant swing low.
2. In the uptrend, wait for a pullback to a fan line (chart shows the shallower 1×4 / 1×8 angles acting as support).
3. Enter on the hold/bounce at that line.
4. Stoploss: below the fan line / below the swing.
5. Target: the next steeper fan angle above, or trend continuation.

**SELL** — mirror: anchor at a swing high, sell rallies that fail at a fan line, stop above it.

### Automation Assessment — the honest problem

**This card is the hardest in the deck to mechanize, and the difficulty is structural, not incidental.**

A Gann fan's angles depend on a price-per-bar scaling ratio chosen by the analyst. The 1×1 line means "one unit of price per one unit of time" — but "one unit of price" is arbitrary and instrument-specific, and on most charting platforms the fan's apparent angles also shift when the chart's zoom or aspect ratio changes. Two traders anchoring at the same pivot with different scaling get different lines and different signals. That is the opposite of what an automated system needs.

There are additional issues:
- **Anchor selection is discretionary.** Which swing low is "significant" is a judgment call; a different anchor produces an entirely different fan.
- **The card's own labelling is inconsistent.** The SELL panel shows "1xB" and "8×14 x3×1", which don't correspond to standard Gann ratios — likely print/scan artifacts, but they mean the intended angle set can't be read reliably from this card.
- **Weak evidential base.** Gann's methods have never been shown to outperform simpler trend tools in published testing; the observed "support" at fan lines is largely indistinguishable from any rising line drawn through a trend.

### Futures Adaptability Assessment (Skill 14)

**Verdict: not recommended for automation. Lowest priority in the playbook — below even Skill 9.**

If you want to pursue the underlying idea, the tradable content is "diagonal support in a trend," and there are objective substitutes that ARE automatable:
1. **Linear regression channel** — which this very card already draws on the BUY panel. Deterministic (least-squares fit over N bars), scale-invariant, with ±1/2σ channel lines that serve the same "diagonal support/resistance" role. If any part of this card gets built, build this.
2. **ATR-anchored trendlines or Supertrend (Skill 12)** — already scale-invariant and already in the playbook.
3. **Pivot-anchored trendlines** with a fixed, explicit slope rule (e.g. connect swing low to swing low, extend) — objective if the pivot definition is fixed.

Recommendation: record Skill 14 for completeness, do NOT allocate build time to it. Redirect the effort to the linear regression channel variant, which captures the same intuition with reproducible math. If you do want it tested, test the regression channel and Gann fan side by side on the same data — if Gann adds nothing over regression, that settles it empirically rather than by argument.

---

## Skill 15: Swing Trading with Institutional Moves (Supply & Demand Zones)

Zone-based swing trading: identify where large orders were absorbed, then trade price's return to that area. Card 1.5, "Strategies Based On Swings" family. Both panels include a volume pane.

⚠️ **INCOMPLETE — rules side not yet captured.** Chart face only (fifth consecutive). Rules below are read off the annotations.

### What the chart shows

**BUY panel:** A horizontal box (demand zone) is drawn at a price area where an extended sideways cluster formed — circled — accompanied by elevated volume bars beneath. Price later returns, holds above the zone, and Entry is marked just above it with Stoploss just below (inside/under the zone). Target is the prior swing high far to the left, i.e. the origin of the earlier decline.

**SELL panel:** A boxed "Supply Zone" is labelled at the top of the chart. Price rallies back into it, Stoploss sits above the zone, Entry just below it, and Target is marked at a lower support area.

### Inferred Rules (pending text confirmation)

**BUY**
1. Identify a demand zone: an area where price consolidated on heavy volume before a strong move up (institutional accumulation footprint).
2. Wait for price to return to the zone.
3. Entry: on the hold/reaction above the zone.
4. Stoploss: below the zone.
5. Target: prior swing high / the level from which the last decline began.

**SELL** — mirror using a supply zone: heavy-volume consolidation before a strong move down; sell on the return, stop above the zone, target the prior swing low.

### Mechanical Definitions for Automation

- **Zone origin**: a base of N consolidation bars (tight range) immediately preceding a strong impulse move (impulse ≥ 2–3 × ATR within M bars). This "base → impulse" sequence is the objective, testable version of "institutional move."
- **Zone bounds**: high/low of the base bars (conservative: body high/low).
- **Volume confirmation**: base or breakout volume ≥ 1.5–2 × the 20-bar volume average — the same sensor Skill 2 uses, applied to zone qualification rather than breakout timing.
- **Zone freshness**: count touches; a zone that has already been tested 2+ times is largely consumed. Track and expire zones — this matters more than most zone traders admit.
- **Entry trigger**: bar close back out of the zone in the trend direction (same close-based confirmation pattern as Skills 4 and 10), or a stop order above the reaction candle.
- **Target**: prior structural swing extreme; also compute R and enforce a minimum R:R (skip if < 1.5).

### Futures Adaptability Assessment (Skill 15)

**Verdict: adaptable, and the volume component is genuinely meaningful on futures — but zone definition is the make-or-break implementation detail, and it's where most automated supply/demand systems fail.**

What ports cleanly:
- Futures volume is real exchange volume, so the "institutional footprint" premise is testable rather than aspirational (unlike spot FX tick volume).
- Base-then-impulse detection, zone bounds, and close-based re-entry triggers are all mechanical and bar-close evaluable.
- Static zone boundaries → static stop and target → plain bracket orders. Low operational complexity, similar to Skill 13.

Caveats for futures:
1. **"Institutional zone" is a narrative, not a measurement.** What's observable is: a base, an impulse, and elevated volume. Build and test exactly that, and hold it to the same statistical bar as anything else — the story about who was buying doesn't add predictive power on its own.
2. **Zone proliferation**: naive detection marks dozens of zones per session. Without freshness expiry, a strength score (impulse size × volume ratio), and a cap on active zones, the bot will trade noise. This filtering logic is the actual work of the build.
3. **Volume profile is the stronger futures-native alternative.** On ES/NQ, VPOC / value-area / high-volume nodes measure the same "where was size transacted" question with a rigorous, reproducible method and no zone-drawing subjectivity. If this skill gets built, strongly consider implementing it as volume-profile levels rather than hand-styled boxes.
4. **Overlap with existing skills**: Skill 15's zones, Skill 13's pivots, and Skill 8's VWAP all answer "where are the levels?" Rather than three separate level engines, implement one shared levels service with multiple providers (pivots, VWAP/bands, volume-profile nodes, base-impulse zones) and a confluence score. Skills 3, 4, 13 and 15 all become consumers of it.
5. **Swing-tier fit**: this belongs with Skills 2, 10 and 12 in the swing tier — daily/4H/30-min, bar-close cadence, no latency pressure.

---

## Skill 16: Analyzing Pivot Points Using VWAP & Standard Deviations

Mean-reversion between VWAP standard-deviation bands, with the VWAP line itself as the first target. Card 2.3. Chart settings: VWAP (Session, hlc3) with bands at 1, 2 and 3 standard deviations.

⚠️ **INCOMPLETE — rules side not yet captured.** Chart face only (sixth consecutive). Rules below are read off the annotations; band numbers in particular should be confirmed from the text.

### What the chart shows

**BUY panel:** Price sells off to the lower band region. Entry is marked at that extreme with Stoploss just below it. Target 1 is at the VWAP centre line; Target 2 is at the upper band, where price eventually reaches.

**SELL panel:** Price rallies into the upper band. Stoploss sits above the extreme, Entry just below it. Target 1 is the VWAP centre line, Target 2 the lower band.

### Inferred Rules (pending text confirmation)

**BUY**
1. Plot session VWAP (hlc3) with ±1/2/3σ bands.
2. Price reaches the lower band (the card's entry appears to be around the −2σ/−3σ area — confirm which).
3. Entry: on the reaction off the band.
4. Stoploss: below the band / below the reaction low.
5. Target 1: VWAP centre line. Target 2: the opposite (upper) band.

**SELL** — mirror.

### Mechanical Definitions for Automation

- **VWAP + bands**: session-anchored, hlc3 source, σ computed from volume-weighted variance around VWAP. Standard in Pine; straightforward in Python.
- **Band touch**: low ≤ lower band (longs). Add close-based confirmation (close back above the band) to avoid entering during a straight-through breakdown — the card's chart shows a reaction candle, not a naked touch.
- **Scaling out**: Target 1 (VWAP) / Target 2 (opposite band) is a two-stage exit — same structure as Skill 1's 1:2 / 1:4 and Skill 13's R1/R2. Requires ≥ 2 contracts, same as Skill 1's caveat.
- **σ-band note**: the extreme bands are reached rarely by construction. Expect low signal frequency; measure it before assuming the strategy is tradable at your desired trade count.

### Futures Adaptability Assessment (Skill 16)

**Verdict: strong futures fit — and it completes the VWAP toolkit alongside Skill 8. Same caveat class as every mean-reversion card: it needs a trend filter or it will fade trend days into the ground.**

What ports cleanly:
- Session VWAP with σ bands is standard and meaningful on ES/NQ; the bands quantify "how stretched" objectively, replacing the vaguer "near the band" language of Skill 9.
- Static-ish targets (VWAP line, opposite band) recompute per bar but change slowly on 5-min+ charts — modest live-management burden.
- Directly reuses the VWAP module built for Skill 8; this is the same infrastructure with different entry/exit rules.

Caveats for futures:
1. **Trend days are the killer.** On a directional futures day price can ride the +2σ band for hours; shorting each touch is how mean-reversion systems die. Mandatory gate: only take band fades when VWAP itself is flat (|VWAP slope| below a threshold) or when the day is classified as rotational. This is the single most important condition to implement, and the card almost certainly doesn't state it.
2. **Relationship to Skill 8**: Skill 8 buys VWAP support in trend with RSI timing; Skill 16 fades the outer bands back to VWAP. They are opposite-direction uses of the same indicator and must not run simultaneously on the same instrument — the regime classifier decides which is active.
3. **Which band?** −2σ vs −3σ materially changes frequency and hit rate. The chart is ambiguous; resolve from the text side, then test both regardless.
4. **RTH anchoring**: same requirement as Skill 8 — anchor to the RTH open, keep backtest and live identical.
5. **Early-session instability**: σ bands are wide and erratic in the first bars of a session. Delay activation until VWAP has matured (same guard as Skill 8).
6. **Playbook fit**: with Skill 8 and Skill 16, VWAP now supports both a trend-pullback and a range-fade module — a clean pair for the regime router.

---

## Skill 17: Donchian Channel and Pullback

Trend continuation after a pullback within a Donchian channel. Card 3.6. Chart settings: DC 20 (20-period Donchian channel — upper = highest high, lower = lowest low, mid = their average).

⚠️ **INCOMPLETE — rules side not yet captured.** Chart face only (seventh consecutive). Rules below are read off the annotations; stop and target placement in particular are not marked on this card at all.

### What the chart shows

**BUY panel:** Price is in an uptrend riding the upper channel. "Pullback" labels a retracement back toward the channel mid-line. Entry is circled on the strong green candle that resumes upward off the pullback, and an arrow tracks the mid-line rising beneath the continued advance.

**SELL panel:** Downtrend along the lower channel; "Pullback" marks a bounce up toward the mid-line, and Entry is marked at the red candle where the decline resumes.

### Inferred Rules (pending text confirmation)

**BUY**
1. Plot DC(20). Confirm uptrend — price has recently been making new 20-bar highs (touching/riding the upper channel).
2. Wait for a pullback toward the channel mid-line.
3. Entry: on the resumption candle off the pullback (chart shows a large bullish candle).
4. Stoploss: not marked — sensible options are below the pullback low or below the channel mid-line.
5. Target: not marked — options are the upper channel, or trail the mid-line / lower channel.

**SELL** — mirror.

### Mechanical Definitions for Automation

- **Donchian**: `upper = ta.highest(high, 20)`, `lower = ta.lowest(low, 20)`, `mid = (upper + lower)/2`. Fully deterministic, one parameter.
- **Trend state**: upper channel made a new high within the last N bars (i.e. `upper > upper[N]`), or price closed above mid for K consecutive bars.
- **Pullback**: price retraces to within a tolerance of mid (e.g. touches mid, or comes within 0.25 × channel width of it) without closing below it.
- **Resumption trigger**: bullish close after the pullback, or a stop order above the pullback bar's high (consistent with the deck's other continuation entries — cf. Skills 1, 6, 7).
- **Stop/target must be supplied** — the card leaves them undefined. Suggested defaults for backtest consistency: stop below the pullback swing low; exit on close below mid (a natural trailing rule with the same "trail the line" shape as Skills 10 and 12).

### Futures Adaptability Assessment (Skill 17)

**Verdict: very good futures fit. Donchian channels are the original futures trend system — this is the Turtle framework's core indicator, applied as a pullback entry rather than a breakout entry.**

What ports cleanly:
- Single-parameter, purely price-based, no volume or session dependency: works identically on any instrument or timeframe.
- Bar-close evaluable throughout → Pine webhook alerts viable; Python bot handles trailing.
- The mid-line trail is the same order-management shape as Skill 10's SMA trail and Skill 12's Supertrend trail. One trailing-exit engine serves all three.

Caveats for futures:
1. **Undefined risk is the gap to close before any testing.** Two of the three core parameters (stop, target) aren't on this card. Lock the defaults above before backtesting or results won't be reproducible.
2. **Pullback depth is the real design decision**: shallow pullbacks (to mid) give more signals and lower hit rate; deeper ones (to the far channel) give fewer, better entries but miss strong trends that never retrace. Parameterise depth and test the range rather than hardcoding "to the mid-line."
3. **Channel lag on reversals**: Donchian extremes are backward-looking, so the channel keeps "confirming" a trend for up to 20 bars after it has actually turned. Pair with a faster confirmation (Supertrend flip from Skill 12, or EMA separation from Skill 3) to avoid buying pullbacks in a trend that has already ended.
4. **Parameter honesty**: 20 is the classic default, and testing 10/20/55 (the Turtle set) is reasonable — but pick the period on out-of-sample performance, not by choosing whichever number looks best on the backtest window.
5. **Playbook fit**: swing tier, alongside Skills 2, 10, 12 and 15. Notably, Skill 17 and Skill 12 are near-substitutes (both trend-following with a trailing-line exit). If both test well, run one — not both — on a given instrument to avoid correlated duplicate positions.

---

## Skill 18: Trading with Renko Charts

Renko brick reversal confirmed by two oscillators. Card 3.5. Chart shows a Renko brick series plus two oscillator panes (upper appears to be RSI; lower is a two-line oscillator, most likely Stochastic).

⚠️ **INCOMPLETE — rules side not yet captured** (eighth consecutive chart-only card).

⚠️ **Card labelling appears inverted.** On the BUY panel, both oscillator circles sit at the LOW end of their ranges but are labelled "Overbought Zone." On the SELL panel, both circles sit at the HIGH end but are labelled "Oversold zone." The labels are swapped relative to the plotted positions on both panels. The circle positions are consistent with the sensible strategy (buy from oversold, sell from overbought), so the positions are probably right and the text labels wrong — but confirm from the rules side before building.

### What the chart shows

**BUY panel:** "Formation of green brick" circles the first green brick after a run of red ones. Both oscillators are circled at the bottom of their ranges at the same point (i.e. turning up out of oversold, despite the label).

**SELL panel:** "Formation of red bricks" circles the first red brick(s) after green ones, with both oscillators circled at the top of their ranges.

### Inferred Rules (pending text confirmation)

**BUY**
1. Renko chart (brick size unspecified on this face — critical missing parameter).
2. First green brick forms after a sequence of red bricks (Renko reversal).
3. Both oscillators confirm from the oversold region.
4. Entry: on the reversal brick.
5. Stop/target: not marked — natural choices are 1–2 bricks against the position for the stop, and a trail of one brick behind price.

**SELL** — mirror.

### Automation Assessment — read this before building

Renko is the most treacherous chart type in this deck for backtesting, and the reasons are technical rather than a matter of opinion:

1. **Bricks are price-based, not time-based.** A Renko series discards the time axis, so bar-close logic, session filters, and time stops all need reworking. Nothing built for the other 17 skills transfers directly.
2. **The last brick is not final until it completes.** A brick forms only when price moves a full brick size; until then the "current" brick can appear and disappear intrabar. Systems that evaluate on brick formation must confirm on a *completed* brick or they will act on data that later vanishes.
3. **Renko backtests are famously over-optimistic.** Because bricks only print after a full brick move, a naive backtest that fills at the brick close assumes fills that were never available at that price. Reported results for Renko systems are routinely inflated for this reason. Any test must fill at realistic prices (the actual market price when the brick completed) plus slippage — and be treated with more skepticism than an equivalent candlestick backtest.
4. **Brick size is the whole strategy and isn't on the card.** Fixed brick size vs. ATR-based brick size produces completely different systems. ATR-based Renko additionally recalculates historical bricks as ATR changes, which introduces repainting of past bars — avoid ATR-Renko for automation; use fixed brick size if pursuing this at all.
5. **Redundancy with existing skills.** A "first opposite-colour brick" signal is a fixed-magnitude reversal filter — functionally close to what Supertrend (Skill 12) and Donchian (Skill 17) already provide with a normal time axis and none of the fill-realism problems.

### Futures Adaptability Assessment (Skill 18)

**Verdict: low priority. The underlying idea (filter out noise, trade confirmed reversals) is sound, but Renko is the wrong vehicle for an automated futures system.** Rank it above Skill 14 (Gann) but below the rest.

If pursued anyway:
- Use fixed brick size in ticks (e.g. 5 ticks ES, 10 NQ), never ATR-based.
- Act only on completed bricks, and fill at the live price when the brick completes, not the brick's nominal close.
- Verify any backtest against a tick-level replay before believing the equity curve. If the tick-level result diverges sharply from the brick-level result, trust the tick-level one.
- Simpler alternative that captures the same intent: apply the two-oscillator confirmation to ordinary time-based candles with an ATR-based noise filter. Same thesis, honest fills, and it reuses the existing bot infrastructure.

---

## Skill 19: Mastering Fractal-Based Trading

Bill Williams fractal signals filtered by the 50 SMA. Card 3.4. Chart settings: Williams Trailing Stops (4, 4, 0, Close) and SMA(50, close).

⚠️ **INCOMPLETE — rules side not yet captured** (ninth consecutive chart-only card).

### What the chart shows

Both panels plot small up/down triangles (fractal markers) above and below price, with the 50 SMA as a single trend line. The annotations are explicit and unusually clear for a chart-only card:

- **BUY panel:** arrow points at the 50 SMA with "Buy above the 50 SMA." Fractal triangles appear throughout, but the tradable ones are those occurring while price is above the SMA.
- **SELL panel:** "Sell below the 50 SMA," with the arrow marking where price crosses down through the SMA and the subsequent decline.

### Inferred Rules (pending text confirmation)

**BUY**
1. Plot fractals and the 50 SMA.
2. Trend filter: price above the 50 SMA.
3. Entry: on a fractal signal in that direction (most likely a break of the most recent up-fractal high — confirm which from the text).
4. Stop: below the most recent down-fractal low (the natural fractal-based stop, and the "trailing stops" name on the indicator suggests this is intended).
5. Target: not marked — trail successive fractals, or exit on close below the 50 SMA.

**SELL** — mirror below the 50 SMA.

### Mechanical Definitions for Automation

- **Fractal (Bill Williams)**: an up-fractal is a bar whose high exceeds the highs of the two bars on either side (5-bar pattern); down-fractal is the mirror on lows. Fully deterministic.
- **⚠️ Fractals confirm two bars late.** The middle bar can only be identified as a fractal after two further bars have closed. This is the defining implementation constraint: a fractal "at" bar N is not known until bar N+2. Any backtest that marks the signal at bar N and fills there is looking ahead and will overstate results. Fill no earlier than bar N+2's open.
- **Trend filter**: `close > ta.sma(close, 50)` for longs.
- **Entry trigger**: stop order at the confirmed up-fractal high, consistent with the deck's other stop-entry setups.
- **Fractal trailing stop**: move the stop to each new confirmed down-fractal low as the trend advances — same trailing-engine shape as Skills 10, 12 and 17.

### Futures Adaptability Assessment (Skill 19)

**Verdict: good futures fit and clean to automate — provided the two-bar confirmation lag is handled honestly. The 50 SMA filter is doing most of the work here.**

What ports cleanly:
- Fractal geometry and SMA are purely price-based, instrument-agnostic, and single-parameter.
- Bar-close evaluable → Pine alerts fine; Python bot manages the fractal trail.
- Fractal-based stops are naturally structural (they sit at real swing points where stops cluster), which tends to behave better on futures than fixed-tick stops.

Caveats for futures:
1. **The confirmation lag is the whole ballgame.** Two bars on a 30-min chart is an hour; on a daily chart it's two days. On fast futures moves the fractal high may be far behind price by the time it confirms. Measure the average price distance between fractal confirmation and the entry level before assuming the setup is tradable — if entries routinely arrive after the move, the strategy is a mirage regardless of how the backtest looks.
2. **Do not use a "current bar" fractal in live code.** Some platform implementations plot provisional fractals that later disappear. Require the two subsequent completed bars, always.
3. **50 SMA whipsaw at the crossover**: price oscillating around the SMA flips the filter repeatedly. Add a buffer (close beyond SMA by ≥ 0.25 × ATR) or require N consecutive closes on one side — same fix recommended for Skill 13's pivot bias.
4. **Substantial overlap with Skills 12 and 17.** Trend filter + structural trailing stop is now the third implementation of one idea (Supertrend trail, Donchian mid trail, fractal trail). These are near-substitutes; pick the one that tests best per instrument rather than running all three.
5. **Playbook fit**: swing tier. Its distinct contribution is the fractal trailing stop, which is arguably the best of the three trailing mechanisms for the quadrant SL tool to eventually consume, since fractal levels are structural rather than formulaic.

---

## Skill 20: Mastering Elliott Wave Theory

Trading the impulse/corrective wave structure. Card 3.3. Chart shows a 5-wave impulse (1-2-3-4-5) followed by an A-B-C correction.

⚠️ **INCOMPLETE — rules side not yet captured** (tenth consecutive chart-only card).

### What the chart shows

**BUY panel:** Wave (1) is labelled "Impulsive," wave (2) "Corrective." Two long entries are marked:
- Entry after wave (2) completes, Stoploss at the wave (2) low, Target at wave (3).
- Entry after wave (4) completes, Stoploss at the wave (4) low, Target at wave (5).
The subsequent A-B-C decline is labelled but not traded on this panel.

**SELL panel:** After the 5-wave advance tops, a short is taken following wave (B): Entry below B, Stoploss at the (B) high, Target at wave (C).

### Inferred Rules (pending text confirmation)

**BUY**
1. Identify an impulsive advance (wave 1) and its corrective pullback (wave 2).
2. Entry: on resumption after wave 2 holds above the wave 1 origin.
3. Stoploss: wave 2 low.
4. Target: projected wave 3 high.
5. Repeat at wave 4 for the wave 5 leg.

**SELL**
1. After a completed 5-wave advance, wait for the A-B corrective bounce.
2. Entry: on the roll-over below B.
3. Stoploss: B high. Target: projected C low.

### Automation Assessment — be honest about what's mechanical here

Elliott Wave is the most-debated framework in the deck, and the reasons matter for a bot:

1. **Wave counts are not unique.** For most price series, several valid counts coexist under Elliott's rules, and practitioners routinely revise counts as new bars arrive. A label that changes retroactively is, for automation purposes, a repainting signal — the same defect flagged for ATR-Renko in Skill 18.
2. **The rules that ARE hard**: wave 2 cannot retrace beyond the start of wave 1; wave 3 is never the shortest of 1/3/5; wave 4 cannot overlap wave 1's territory (in standard impulses). These are codable constraints — but they *validate* a count after the fact, they don't *select* one in real time.
3. **Prospective vs. retrospective.** The card's chart is drawn with completed waves visible. Live, at the moment of the wave-2 entry, you do not yet know whether it's wave 2 of an impulse, wave B of a correction, or the start of a trend reversal. Every Elliott chart looks obvious in hindsight; that's the failure mode to guard against.
4. **What survives stripping the labels**: the actual trades shown are (a) buy a pullback that holds above the prior swing low, targeting a new high, and (b) sell a lower-high bounce in a topping structure. Those are ordinary HH/HL structural pullback trades — and Skill 1 (two-legged pullback) already codifies essentially the same entry without any wave counting.

### Futures Adaptability Assessment (Skill 20)

**Verdict: not recommended as an automated strategy. Rank alongside Skill 14 (Gann) at the bottom of the build list — though for a different reason: Gann's problem is arbitrary scaling, Elliott's is non-unique, revisable counts.**

If you want the value without the subjectivity:
1. **Implement the trade, not the theory.** The wave-2 entry is Skill 1's pullback with a swing-low stop. Already in the playbook, already mechanical. Build once, use for both.
2. **Fibonacci retracement zones as an objective proxy**: "pullback holds the 50–61.8% retracement of the prior impulse leg" captures most of the practical wave-2/wave-4 logic with deterministic math and no labelling.
3. **If you ever want to test Elliott properly**: encode only the hard rules as *filters* on an existing pullback strategy (e.g. reject signals where the pullback exceeds 100% of the prior leg), and measure whether the filter adds anything over the base strategy. That's a clean A/B test and the only way to settle it with data rather than debate.

### Deck-wide note at Skill 20

Twenty cards in, a clear tiering has emerged:
- **Build first (mechanical, complete, futures-native):** 13 (pivots), 10 (BB squeeze), 8 (VWAP+RSI), 12 (Supertrend+RSI), 6 (EMA7 scalp), 3 (EMA S/R).
- **Build second (mechanical, needs defined parameters):** 1, 2, 7, 16, 17, 19, 15.
- **Provisional / needs source clarification:** 9 (garbled rule), 11 (rules missing, filter role), 18 (Renko fill realism).
- **Not recommended for automation:** 14 (Gann), 20 (Elliott).
- **Signal only, sizing discarded:** 5 (martingale).

---

## Skill 21: Smart Money Concept

Order-block / liquidity-sweep entries at marked structural levels. Card 3.2.

⚠️ **INCOMPLETE — rules side not yet captured** (eleventh consecutive chart-only card). SMC terminology varies widely between teachers, so the rules text matters more than usual here — the chart alone can't disambiguate which SMC variant is intended.

### What the chart shows

**BUY panel:** A horizontal level is drawn from a prior high. Price declines beneath it; the circled region shows a push down followed by a strong reclaim back up through the level. Entry is marked at the level, Stoploss below the circled low. A separate boxed band sits lower on the chart with arrows connecting it to the entry — most likely the origin zone (order block) or a measured-move reference.

**SELL panel:** A boxed band (supply zone / order block) is drawn at a level. Price rallies up into the box, Stoploss is placed above the high made inside it, and Entry is at the lower edge of the box as price rejects and rolls over.

### Inferred Rules (pending text confirmation)

**BUY**
1. Mark a structural level / order block from prior price action.
2. Wait for price to sweep below it (liquidity grab / stop run) and then reclaim it.
3. Entry: on the reclaim of the level.
4. Stoploss: below the sweep low.
5. Target: not marked — likely the opposing structural level or the prior high.

**SELL** — mirror: price sweeps into a supply zone above, fails, entry on the rejection with stop above the sweep high.

### Mechanical Definitions for Automation

The tradable core is objectively codable if you ignore the vocabulary:
- **Sweep / stop run**: price trades beyond a prior swing extreme (or session high/low) by ≤ k ticks, then closes back inside within N bars. This "poke and reclaim" is fully mechanical.
- **Order block**: the last opposite-colour candle before the impulse that broke structure — deterministic once "impulse" and "break of structure" are defined numerically (impulse ≥ 2 × ATR; BOS = close beyond the prior swing point).
- **Entry trigger**: close back above the level (longs), consistent with the close-based confirmation used in Skills 4, 10, 15 and 16.
- **Stop**: beyond the sweep extreme + 2–4 ticks buffer (futures sweep behaviour — see Skill 4's note).

### Futures Adaptability Assessment (Skill 21)

**Verdict: the mechanical core is a good futures fit — genuinely so, because stop runs at obvious levels are a real, observable feature of index futures. But this card overlaps almost entirely with Skill 15, and SMC's framing adds vocabulary rather than new signal.**

What actually works on futures:
- Liquidity sweeps at prior-day highs/lows, overnight extremes and session opens are well documented on ES/NQ. Resting stops cluster at those levels, and price frequently pokes through and reverses. This is the one part of the SMC framework with a clear structural rationale on futures specifically.
- Everything needed is already being built for other skills: Skill 13's pivot/session levels supply the sweep targets, Skill 15's base-impulse detector supplies the order blocks, and Skill 4's close-back-through logic supplies the trigger.

Honest caveats:
1. **Terminology inflation.** "Order block," "liquidity grab," and "smart money" describe the same observable events as Skill 15's supply/demand zones and Skill 4's failed breaks. The narrative about institutional intent isn't measurable and adds no predictive power on its own — build and test the price behaviour, not the story.
2. **Heavy overlap with Skill 15 — do not build twice.** Implement one zone/sweep module. If this card's rules text turns out to specify something Skill 15 doesn't (a specific BOS sequence, a fair-value-gap condition), add it as a parameter to that module rather than a separate strategy.
3. **Sweep definition is where the edge lives or dies.** Too loose and every wick qualifies; too tight and nothing triggers. This threshold needs proper parameter testing, not a default.
4. **Discretion risk.** SMC as taught is highly discretionary — practitioners can label almost any reversal after the fact. The discipline for automation is to fix the numeric definitions in advance and accept whatever the backtest says, rather than tuning the definitions until the historical chart looks clean.
5. **Priority**: fold into the Skill 15 build (swing tier). Not a separate line item.

---

## Skill 22: Basics of Dow Theory

Trend definition by swing structure, traded on the break of the prior swing extreme. Card 3.1.

⚠️ **INCOMPLETE — rules side not yet captured** (twelfth consecutive chart-only card).

### What the chart shows

**BUY panel:** Price bottoms and begins making higher lows. A horizontal line marks the prior swing high on the left. Entry is at the break above that level; Stoploss sits at the swing low beneath the base. Target is a higher horizontal level reached later in the advance.

**SELL panel:** Downtrend making lower highs. Entry is marked at the break below a prior swing low, Stoploss above the most recent lower high, Target far below at a later support level.

### Inferred Rules (pending text confirmation)

**BUY**
1. Establish an uptrend by structure: higher highs and higher lows.
2. Entry: on the break/close above the prior swing high (structure confirmation).
3. Stoploss: below the most recent higher low.
4. Target: the next structural resistance level.

**SELL** — mirror: lower highs and lower lows, entry on the break below the prior swing low, stop above the last lower high, target the next support.

### Mechanical Definitions for Automation

- **Swing points**: pivot highs/lows with a fixed lookback/lookforward (e.g. `ta.pivothigh(5,5)`). Note the same confirmation-lag issue as Skill 19 — a pivot with 5 bars right isn't known until 5 bars later. Use it for the *level*, and trigger on the break, which is real-time.
- **Trend state**: last two confirmed pivot highs rising AND last two pivot lows rising = uptrend. Fully deterministic.
- **Entry**: stop order above the prior confirmed swing high, or a close beyond it (close-based is more robust against sweeps — see Skill 21).
- **Stop**: most recent confirmed higher low.
- **Target**: next structural level, or reuse the playbook's R-multiple ladder (1:2 / 1:4) for consistency with Skill 1.

### Futures Adaptability Assessment (Skill 22)

**Verdict: highly adaptable and foundational — but recognise what this card actually is. Dow theory's HH/HL structure is the substrate that Skills 1, 15, 20, 21 and 22 all sit on top of. This is the base layer, not a twenty-second competing strategy.**

What ports cleanly:
- Pivot detection and structure state are pure price geometry: instrument-agnostic, timeframe-agnostic, one parameter.
- Break-of-structure entries with swing stops are exactly the trade Skill 1 (two-legged pullback), Skill 20 (Elliott, stripped of labels) and Skill 21 (SMC, stripped of vocabulary) all describe in different dialects.
- Static level-based stops and targets → plain brackets, low operational complexity.

Caveats for futures:
1. **Breakout vs. pullback entry is the fork.** This card enters ON the structural break; Skill 1 enters on the pullback WITHIN the trend. Same framework, different timing, materially different fill quality and hit rate on futures. Test both off the same structure engine — that comparison is probably worth more than any single new strategy.
2. **Sweep risk at obvious structure.** Prior swing highs are exactly where stops sit on ES/NQ, so breaks get faded routinely. Close-based confirmation plus a small buffer (0.25 × ATR beyond the level) is close to mandatory — this is the same issue flagged in Skills 4, 13 and 21.
3. **Pivot lookback sets the timeframe.** A 3-bar pivot and a 10-bar pivot define completely different "trends" on the same chart. Pick per timeframe and hold it fixed across backtest and live.
4. **Build recommendation — this is the consolidation point.** Rather than 22 separate strategies, the playbook now clearly resolves into a small number of shared services:
   - **Structure engine** (this card): pivots, HH/HL state, break detection → consumed by 1, 15, 19, 21, 22.
   - **Levels service**: pivots/session levels (13), VWAP + bands (8, 16), volume-profile/zones (15, 21).
   - **Regime classifier**: EMA separation (3), ADX, VWAP slope (16) → routes trend vs. range strategies.
   - **Trailing-exit engine**: SMA (10), Supertrend (12), Donchian mid (17), fractal (19).
   - **Risk manager**: per-trade R budget, tick rounding, session guards, daily loss limit, news blackout.
   Every card in the deck is then a thin signal module over those five services. That is the actual architecture the playbook has been pointing at since roughly Skill 8.

---

## Skill 23: Narrow CPR with Trend Following

Central Pivot Range width as a day-type forecast, traded as a directional breakout. Card 2.8. Chart indicator: "CPR by KGS" — Central Pivot Range (Pivot, TC, BC) with additional support/resistance pivot levels plotted.

⚠️ **INCOMPLETE — rules side not yet captured** (thirteenth consecutive chart-only card).

### What the chart shows

**BUY panel:** A tight (narrow) CPR band is plotted. Price opens near it, and the circled area shows price holding above the band. Entry is marked just above the CPR, Stoploss below it, and Target at a higher pivot resistance line reached after a sustained advance.

**SELL panel:** Again a narrow CPR. Price fails at the band; Entry is marked below it, Stoploss above the CPR/recent high, and Target at a lower pivot support line circled at the end of the decline.

### Concept

- **CPR** = three lines from the prior session: Pivot = (H+L+C)/3; BC = (H+L)/2; TC = 2×Pivot − BC.
- **CPR width = |TC − BC|.** A narrow CPR means the prior session's range and close were tightly clustered, which historically associates with a trending (directional) day; a wide CPR associates with rangebound/rotational days.
- The card's strategy: on a narrow-CPR day, take the directional break away from the band and hold for a trend move to the outer pivot levels.

### Inferred Rules (pending text confirmation)

**BUY**
1. Compute CPR from the prior session. Require it to be narrow (threshold unspecified — see below).
2. Price holds/breaks above the CPR band.
3. Entry: above the CPR (chart shows entry just above the TC line).
4. Stoploss: below the CPR band / below BC.
5. Target: the next pivot resistance (R1/R2 equivalent on the plotted set).

**SELL** — mirror below the band.

### Mechanical Definitions for Automation

- **CPR math is fully deterministic** — same category as Skill 13's pivots, computed once per session before the open.
- **"Narrow" needs a threshold and the card doesn't give one.** Use a relative measure, not an absolute: CPR width / prior-session range, or CPR width as a percentile of its own last 20–60 sessions. An absolute tick threshold won't transfer between ES and NQ or across volatility regimes.
- **Break confirmation**: close beyond TC (longs) / BC (shorts), with a buffer — same sweep caution as Skills 13, 21, 22.
- **Targets**: static pivot levels → plain bracket orders.

### Futures Adaptability Assessment (Skill 23)

**Verdict: strong futures fit, and notable as the only card in the deck that forecasts DAY TYPE rather than generating a signal. That makes it more valuable as a regime input than as a standalone strategy.**

What ports cleanly:
- Prior-session OHLC math, computed pre-open, zero lag, zero repainting. Same operational simplicity as Skill 13.
- Static stops and targets → plain brackets, no live modification.
- Directly extends the pivot module already planned for Skill 13 — CPR is three extra lines from the same inputs, so the incremental build cost is close to zero.

Caveats for futures:
1. **RTH vs. ETH again.** Identical issue to Skill 13: the session definition changes every CPR value. Decide once, apply everywhere.
2. **The narrow/wide claim is testable — so test it.** "Narrow CPR predicts trend days" is an empirical assertion, widely repeated in Indian equity/index trading circles but not something to take on faith for ES/NQ. Before building the strategy, run the cheap prerequisite study: classify sessions by CPR-width percentile, then measure realised day range or directional persistence per bucket. If narrow CPR days don't actually trend more on your instrument, the strategy has no foundation and you've saved yourself the build.
3. **Threshold choice is the main parameter risk.** With a percentile threshold, the bottom 20–30% of sessions is a reasonable starting band; tune out-of-sample.
4. **Best use is as a gate, not a signal.** Rather than a standalone strategy, CPR width can route the whole playbook: narrow-CPR day → enable trend strategies (10, 12, 17, 22); wide-CPR day → enable range strategies (4, 16). This slots directly into the regime classifier identified at Skill 22 and may be its single cheapest, highest-value input.
5. **Playbook fit**: build with Skill 13 as one "session levels + day type" module.

---

## Skill 24: Wide CPR with Trend Following

The companion card to Skill 23 — same CPR indicator, wide-band condition. Card 2.7. Indicator: "CPR by KGS" (Pivot, TC, BC plus outer pivot levels).

⚠️ **INCOMPLETE — rules side not yet captured** (fourteenth consecutive chart-only card).

### What the chart shows

**BUY panel:** A wide CPR band is plotted. Price is trending up above it; the circled area shows price dipping back to the upper CPR line and holding. Entry is marked just above that reaction, Stoploss below the CPR line, Target at a higher pivot resistance.

**SELL panel:** Price rallies up into the CPR band from below and is rejected at it (circled). Entry is marked below the rejection, Stoploss above the CPR line, Target at a lower pivot level circled at the end of the decline.

### Concept — and how it differs from Skill 23

Both cards are titled "trend following," but the mechanics on the charts are different, and the difference is the point:

- **Skill 23 (narrow CPR):** entry is a BREAKOUT *away* from a tight band. The band is small, price leaves it, and the trade rides the expansion.
- **Skill 24 (wide CPR):** entry is a REACTION *at* the band. The band is large enough to act as a genuine support/resistance zone, so price is traded off it in the direction of the prevailing move.

This is consistent with standard CPR doctrine: narrow CPR → expect expansion/trend; wide CPR → expect the band to hold as a level and the day to rotate around it. Confirm against the rules text, since the shared "trend following" title obscures the distinction.

### Inferred Rules (pending text confirmation)

**BUY**
1. CPR is wide (threshold unspecified — use a percentile, as in Skill 23).
2. Prevailing move is up, price above the CPR band.
3. Entry: on the hold/bounce at the upper CPR line (TC).
4. Stoploss: below the CPR line / below the reaction low.
5. Target: next pivot resistance.

**SELL** — mirror: price rejects at the CPR from below, entry below the rejection, stop above the band, target the next pivot support.

### Mechanical Definitions for Automation

- **CPR math**: identical to Skill 23 — Pivot = (H+L+C)/3, BC = (H+L)/2, TC = 2×Pivot − BC. Same module, no extra build.
- **"Wide"**: top 20–30% of the CPR-width percentile distribution over the last 20–60 sessions (the complement of Skill 23's narrow bucket).
- **Reaction at the band**: price touches/enters the CPR zone and closes back out on the favourable side — structurally the same test as Skill 4's pinbar-at-zone and Skill 16's band fade. Reuse that code.
- **Direction filter**: the card's setup requires a prevailing move; define it explicitly (EMA separation from Skill 3, or position relative to the day's opening range).

### Futures Adaptability Assessment (Skill 24)

**Verdict: adaptable, and it completes the CPR pair — but it is best understood as the "range/rotation" branch of one CPR system, not a separate strategy.**

What ports cleanly:
- Zero incremental infrastructure: same CPR module, same levels service, same close-back-through trigger already required by Skills 4, 15, 16 and 21.
- Static stops and targets → plain brackets, pre-open computable, no repainting.

Caveats for futures:
1. **Same empirical prerequisite as Skill 23.** Before building either branch, test whether CPR width actually predicts day type on ES/NQ. One study answers both cards: bucket sessions by CPR-width percentile, then measure realised range, directional persistence, and how often the CPR band holds as support/resistance. If the relationship is weak, both cards fall together — and that's a cheap thing to learn early.
2. **Wide CPR days can still trend.** The doctrine is probabilistic, not deterministic. Because this branch fades into the band, it carries the same trend-day risk as Skills 4 and 16 — keep a hard stop beyond the band and don't re-enter repeatedly on a directional day.
3. **Do not run both branches simultaneously on the same session.** CPR width selects exactly one: narrow → Skill 23 breakout mode; wide → Skill 24 reaction mode. That mutual exclusivity is a feature — it's a clean, pre-open, deterministic regime switch, which is rarer and more useful than either signal alone.
4. **Build as one module.** "CPR day-type router" with two child behaviours, feeding the regime classifier from Skill 22. Combined with Skill 13's pivots, this becomes a single session-levels-and-day-type service.

---

## Skill 25: Double RSI

Two RSIs of different lengths — a fast one for timing, a slow one for context. Card 2.6. Chart settings: RSI(14, close, SMA 14, 2) with bands, and RSI(60, 14, close, SMA 14, 2).

⚠️ **INCOMPLETE — rules side not yet captured** (fifteenth consecutive chart-only card).

⚠️ **The 50-level filter reads counter-intuitively and needs the text to resolve.** On the BUY panel the slow RSI is circled and labelled "below 50"; on the SELL panel it is circled and labelled "above 50." Taken at face value that is a mean-reversion filter (buy when longer-term momentum is washed out). But the same label pattern was inverted on Skill 18's card, so a printing error is also possible. Both readings are given below — do not build until this is settled, because the two are opposite strategies.

### What the chart shows

**BUY panel:** Entry is circled at the low of a decline, with Stoploss just beneath it. The fast RSI(14) is circled at its LOWER band at that moment. Target is far higher, and the fast RSI is circled at its UPPER band there. The slow RSI(60) is circled with the "below 50" annotation.

**SELL panel:** Entry near a high with Stoploss above; fast RSI circled at its UPPER band at entry, at its LOWER band at target; slow RSI(60) circled with "above 50."

The fast-RSI role is unambiguous: **oversold entry → overbought exit for longs, and the mirror for shorts.** That is a mean-reversion timing engine.

### Two possible readings of the slow RSI

**Reading A — mean-reversion context (matches the labels as printed):** slow RSI below 50 means longer-term momentum is depressed; combined with fast RSI at the lower band, the setup is a deep washed-out bounce. Coherent, and consistent with the fast-RSI mechanics.

**Reading B — trend filter (matches conventional practice, implies a misprint):** slow RSI above 50 for longs, below 50 for shorts, i.e. buy dips only in an established uptrend. This is the standard double-RSI construction and is what most implementations do.

Reading B is the more common design and generally the more robust on futures; Reading A is what the card actually says. Resolve from the text side before writing code.

### Mechanical Definitions for Automation

- **Fast RSI**: `ta.rsi(close, 14)` with the card's SMA(14) smoothing and ±2 band overlay.
- **Slow RSI**: labelled "RSI 60" — most likely RSI with a 60-period length on the same chart, though it could denote RSI(14) computed on the 60-minute timeframe. These are different indicators; confirm which. If multi-timeframe, note the higher-timeframe value only updates on 60-min closes and must not be read mid-bar in a backtest (lookahead risk).
- **Entry**: fast RSI crosses back up out of its lower band while the slow-RSI condition holds.
- **Exit**: fast RSI reaches the upper band (the card's Target markers).
- **Stop**: below the entry swing low, per the chart.

### Futures Adaptability Assessment (Skill 25)

**Verdict: mechanically clean and cheap to build — every component is already in the stack — but its value depends entirely on which reading is correct, and on the trend-day guard.**

What ports cleanly:
- RSI is already in the existing bot (Skills 8, 12 also use it). Two lengths is a trivial extension.
- Bar-close evaluable throughout; Pine alerts fine.
- Band-based entry/exit gives explicit, testable thresholds rather than the vaguer language in several other cards.

Caveats for futures:
1. **If Reading A is correct, this is a counter-trend fade** and inherits the standard danger: on trending futures sessions the fast RSI can sit at an extreme for hours. It would need the same VWAP-slope / ADX gate mandated for Skills 4 and 16.
2. **If Reading B is correct**, it is a trend-pullback system and is materially safer — closer in spirit to Skill 8 (dip-buying with RSI timing inside a trend). In that case, check the overlap: Skill 8 already does this with VWAP as the location filter, and running both would produce correlated signals.
3. **"RSI 60" ambiguity is a real fork**, not a detail. A 60-period RSI on a 5-min chart and RSI(14) on the 60-min chart behave differently and have different data plumbing (the latter needs proper higher-timeframe handling with no lookahead).
4. **Exit-on-opposite-band has no price stop.** Same weakness noted for Skill 8's RSI exit: keep the structural stop and consider a time-stop, since the fast RSI may never reach the far band.
5. **Priority**: low-cost addition to the existing RSI module, but not a build-first card — resolve the two ambiguities first, then A/B it against Skill 8 rather than assuming it adds something new.

---

## Skill 26: Wait and Trade the Pullback

Breakout-retest entry at pivot levels — wait for the level to be broken, then enter on the pullback that holds it. Card 2.5. Indicator: Pivots, Traditional, Auto timeframe, 150 pivots back.

⚠️ **INCOMPLETE — rules side not yet captured** (sixteenth consecutive chart-only card).

### What the chart shows

**BUY panel:** Price advances through R2. Rather than buying the break, the setup waits: price pulls back to R2 and holds it (circled). Entry is marked at that hold with Stoploss just below the R2 line. Target is at R3, reached after a sustained advance.

**SELL panel:** Price is rejected at an upper pivot (first circle), then breaks down through a level. It retests that broken level from beneath (second circle), and Entry is marked below the retest with Stoploss at the retest high. Target is a lower pivot level near P/S1.

### Inferred Rules (pending text confirmation)

**BUY**
1. Plot Traditional pivots.
2. Price breaks and closes above a pivot resistance level (e.g. R2).
3. Wait — do not enter on the break.
4. Entry: when price pulls back to the broken level and holds it (level now acting as support).
5. Stoploss: below the pivot level / below the pullback low.
6. Target: the next pivot level up (R3).

**SELL** — mirror: level breaks down, retest from below fails, entry on the rejection, stop above the retest high, target the next pivot down.

### Mechanical Definitions for Automation

- **Break**: close beyond the pivot level (close-based, with buffer — see Skill 13).
- **Pullback / retest window**: price returns to within a tolerance of the level (e.g. ±0.25 × ATR) within N bars of the break. Expire the setup if the retest doesn't arrive in time.
- **Hold confirmation**: the retest bar closes back on the favourable side of the level — same close-back-through test already required by Skills 4, 15, 16, 21 and 24. Reuse that code.
- **Invalidation**: a close back through the level in the wrong direction cancels the setup entirely.
- **Stop and target**: static pivot levels → plain bracket orders.

### Futures Adaptability Assessment (Skill 26)

**Verdict: strong futures fit, and it directly answers the open question raised at Skill 22 — this is the pullback counterpart to Skill 13's breakout entry, on the same level set.**

Why this matters more than it looks:
- Skill 13 buys the break of a pivot level. Skill 26 waits for the break, then buys the retest. Same levels, same targets, same infrastructure — different timing.
- That pairing is directly testable and the comparison is genuinely informative: breakout entries have higher fill rates but worse average entry price and more false starts; retest entries have better prices and tighter stops but miss the moves that never pull back. On ES/NQ, where obvious breakout levels get swept routinely (flagged in Skills 4, 21, 22), the retest version often survives that behaviour better — but that's a hypothesis to measure, not a conclusion.
- Recommendation: implement both as two entry modes on one pivot-level engine, run them over the same data, and let the results decide per instrument and timeframe. This costs almost nothing beyond Skill 13's build and answers a structural question about the whole playbook, since the same breakout-vs-pullback fork recurs in Skills 1/22, 2/26 and 10/17.

Caveats for futures:
1. **Missed-move risk is the real cost.** In strong trends price often doesn't return to the broken level. Track the miss rate in backtest; if it's high, consider a hybrid (partial size on the break, add on the retest).
2. **Retest window length is the key parameter.** Too short and valid setups expire; too long and the "retest" is really a failed breakout. Test the range.
3. **"Auto 150" pivot setting**: 150 pivots back is just plotting history — it doesn't change the levels. Confirm the pivot *timeframe* (daily levels on an intraday chart is the usual intent) and, as with Skill 13, settle RTH vs. ETH once and apply it everywhere.
4. **Priority**: build alongside Skill 13 as the second entry mode of the pivot module. High value, near-zero marginal cost.

---

## Skill 27: Buy/Sell with RSI and Volume Oscillator

RSI extreme confirmed by a volume oscillator reading. Card 2.4. Chart settings: RSI(14, close, SMA 14, 2) with bands, and Volume Oscillator(5, 10).

⚠️ **INCOMPLETE — rules side not yet captured** (seventeenth consecutive chart-only card).

⚠️ **Label error on the SELL panel.** Both annotated zones on the sell side are labelled "Oversold zone," but the circles sit at the TOP of the RSI range and at a volume-oscillator spike — where "overbought" belongs. This is the fourth card in the deck with inverted or garbled labels (see Skills 9, 18, 25). Trust the circle positions over the text, but confirm from the rules side.

### What the chart shows

**BUY panel:** Entry is marked at a base after a decline, Stoploss below the low. RSI(14) is circled in its oversold zone at that moment. The Volume Oscillator is circled at a low reading ("Oversold zone"). Later, "Exit as per RSI" is circled where RSI reaches the upper band.

**SELL panel:** Entry near a high with Stoploss above. RSI circled at the top of its range (mislabelled), Volume Oscillator circled at a spike. "Exit as per RSI" is circled where RSI reaches the lower band.

### Inferred Rules (pending text confirmation)

**BUY**
1. RSI(14) in the oversold zone.
2. Volume Oscillator confirms (low/negative reading — see interpretation note below).
3. Entry: on the turn up from the RSI extreme.
4. Stoploss: below the entry swing low.
5. Exit: when RSI reaches the opposite (overbought) band.

**SELL** — mirror.

### The Volume Oscillator role needs clarifying

Volume Oscillator(5,10) = (EMA5(volume) − EMA10(volume)) / EMA10(volume) × 100. It measures whether short-term volume is expanding or contracting relative to the recent baseline — it is NOT overbought/oversold in the price sense, so the card's zone language is loose.

Two coherent readings, and they imply different systems:
- **Reading A — contraction confirms exhaustion:** a low/negative reading at the RSI extreme means selling pressure has dried up, supporting a reversal. Consistent with the BUY panel's circle at a low VO reading.
- **Reading B — expansion confirms capitulation:** a spike means the final flush is happening, marking the turn. Consistent with the SELL panel's circle at a VO spike.

The two panels appear to circle opposite VO conditions, which is exactly the sort of thing the rules text would settle. Do not guess — this determines whether the filter requires high or low volume, and getting it backwards inverts the strategy.

### Mechanical Definitions for Automation

- **RSI**: already in the stack (Skills 8, 12, 25).
- **Volume Oscillator**: trivial to compute; on futures it uses real exchange volume, so it is meaningful (same advantage noted in Skills 2, 10, 15).
- **Entry**: RSI crosses back out of its band while the VO condition holds.
- **Exit**: RSI reaches the opposite band — same no-price-stop weakness as Skills 8 and 25; keep the structural stop and consider a time-stop.
- **Session baseline caveat**: intraday futures volume has a strong U-shape. A 5/10 volume oscillator partly self-normalises (it is a ratio of two short averages), but at session boundaries it will still distort. Guard the open/close, as with Skill 2.

### Futures Adaptability Assessment (Skill 27)

**Verdict: cheap to build, meaningful volume input, but low novelty — it is Skill 8 with the volume oscillator swapped in for VWAP as the confirmation filter.**

What ports cleanly:
- Both indicators already exist in the stack; this is a recombination, not new infrastructure.
- Bar-close evaluable; Pine alerts fine.
- Volume on futures is real, so the filter has actual information content rather than being a proxy.

Caveats:
1. **Resolve the VO direction first.** Reading A and Reading B are opposite filters. Building before this is settled risks implementing the inverse of the intended strategy — and a backtest would simply show it losing, without revealing why.
2. **Counter-trend exposure.** Like Skills 4, 16 and possibly 25, this fades extremes. It needs the same regime gate; on a trending futures session RSI can sit at a band for hours.
3. **Redundancy check.** The playbook now has four RSI-based mean-reversion variants (8, 16, 25, 27) distinguished only by their confirmation filter — VWAP, σ-bands, slow RSI, volume oscillator. Rather than building all four, build one RSI mean-reversion module with a pluggable confirmation filter and test the four filters against each other on the same data. That is one build and one experiment instead of four of each.
4. **Priority**: low. Add as a filter option to the RSI module once Skills 8 and 16 are running.

---

## Skill 28: RSI Divergence + Bollinger Bands Scalping Strategy

Reversal scalp: price at a band extreme while RSI diverges. Card 5.2, "Scalping" category. Chart settings: BB(20, close, 2, 0) and RSI(14, close, SMA 14, 2).

⚠️ **INCOMPLETE — rules side not yet captured** (eighteenth consecutive chart-only card).

### What the chart shows

**BUY panel:** Price grinds down along the lower Bollinger Band making successive lows. Beneath, a line is drawn under the RSI lows showing RSI holding flat/rising while price falls — bullish divergence. Entry is marked as price turns up, Stoploss below the swing low, Target at the middle band and beyond.

**SELL panel:** Price pushes up along the upper band making higher highs; a line over the RSI highs shows RSI making lower highs — bearish divergence. Entry below the turn, Stoploss above the high, Target at the middle band.

### Inferred Rules (pending text confirmation)

**BUY**
1. Price at/near the lower Bollinger Band.
2. Bullish RSI divergence: price makes a lower low, RSI makes a higher low.
3. Entry: on the turn up after the divergent low.
4. Stoploss: below the swing low.
5. Target: the middle band (20 SMA), per the chart arrows.

**SELL** — mirror at the upper band.

### Automation Assessment — divergence is harder than it looks

The BB half is trivial; the divergence half carries real implementation traps:

1. **Divergence needs pivots on two series, and pivots confirm late.** A swing low in price and the corresponding RSI low are only identifiable after the lookforward bars have closed — the same constraint flagged in Skill 19. A divergence "at" the low is typically confirmed 2–5 bars later. Backtests that mark the entry at the divergent low itself are looking ahead and will be badly inflated.
2. **Many published divergence indicators repaint.** Some redraw divergence lines as new pivots form, changing historical signals. If borrowing a Pine divergence script, verify it uses confirmed pivots only before trusting any backtest built on it.
3. **Divergence persists in trends.** This is the classic failure: in a strong move, RSI can diverge for many bars while price continues. On a 1-min/5-min futures downtrend, the first three divergences are losses and the fourth is the turn. A regime gate is not optional here — same requirement as Skills 4, 16, 27.
4. **Definition choices matter and aren't on the card:** how many bars back to compare, whether to use RSI value at the price pivot or RSI's own pivot, and how much RSI difference counts as divergence. Each changes the signal set materially. Fix them explicitly before testing.

### Mechanical Definitions for Automation

- **Price pivot**: `ta.pivotlow(left, right)` with a fixed setting; the RSI comparison uses the RSI value at those confirmed pivot bars.
- **Bullish divergence**: `price_low[1] > price_low[0]` (lower low) AND `rsi_at_low[1] < rsi_at_low[0]` (higher RSI low), within a bounded bar distance.
- **Band condition**: the divergent low occurs at or below the lower BB.
- **Entry**: earliest permissible bar is the pivot-confirmation bar — no earlier.
- **Exit**: middle band (20 SMA), recomputed per bar; same dynamic-target handling as Skills 5, 6 and 10.

### Futures Adaptability Assessment (Skill 28)

**Verdict: tradable idea, but the least honest-to-backtest card in the scalping tier. Rank it below Skills 6, 7 and 8, and above the Renko/Gann/Elliott group.**

What ports cleanly:
- BB and RSI are standard and already in the stack.
- The middle-band target is objective, and the swing-low stop is structural.

Caveats for futures:
1. **Confirmation lag versus scalping timeframe is the core tension.** On a 1-min chart, waiting 3–5 bars for pivot confirmation can mean entering after most of the reversal. Measure the distance between the divergent low and the first legal entry price; if it routinely exceeds a meaningful share of the move to the middle band, the strategy doesn't survive its own lag.
2. **Trend-day exposure**, as above — mandatory gate.
3. **Overlap**: this is the fifth RSI mean-reversion variant (8, 16, 25, 27, 28). It belongs in the same pluggable-filter module recommended at Skill 27, with "RSI divergence" as one more confirmation option rather than a separate build.
4. **If built, validate against a naive baseline.** Compare divergence-plus-band against band-touch alone. Divergence adds complexity and lag; it needs to earn its place rather than be assumed superior.

---

## Skill 29: Volatility Contraction Pattern (VCP)

A sequence of progressively shallower pullbacks beneath a flat resistance level, resolved by a breakout. Card 7.6. (This is the pattern popularised by Mark Minervini in equity swing trading.)

⚠️ **INCOMPLETE — rules side not yet captured** (nineteenth consecutive chart-only card).

### What the chart shows

Price advances, then builds a base under a horizontal resistance line drawn across the highs. Three contractions are labelled:
- **First Pullback** — deep and wide, spanning many bars.
- **Second Pullback** — noticeably shallower and shorter.
- **Third Pullback** — shallower still, tight against the resistance line.

Price then breaks above the line and trends up strongly. No entry/stop/target markers appear on this face — the card is illustrating the pattern rather than the trade.

### Concept

Each successive pullback being smaller means supply is being absorbed: sellers are progressively less willing to push price down, and the range tightens against a fixed ceiling. The breakout through that ceiling is the trigger. It is the same underlying thesis as Skills 2 and 10 (compression precedes expansion) but measured through *pullback depth sequence* rather than volume or band width.

### Inferred Rules (pending text confirmation)

**BUY**
1. Prior uptrend into the base.
2. Two or more pullbacks, each shallower than the last (the card shows three).
3. A flat-ish horizontal resistance across the base highs.
4. Entry: breakout above that resistance.
5. Stop: below the final (shallowest) pullback low — the natural placement, and what makes the pattern attractive, since risk is smallest at the entry point.
6. Target: not marked; measured move or a trailing exit.

The card shows no SELL construction, consistent with VCP being a long-side equity pattern in its original form.

### Mechanical Definitions for Automation

- **Contraction sequence**: identify successive swing lows/highs; require each pullback depth (high−low as % or ATR multiple) to be smaller than the previous — e.g. depth₂ ≤ 0.7 × depth₁, depth₃ ≤ 0.7 × depth₂. Duration typically contracts too; can be required or left optional.
- **Resistance line**: highest high of the base, with tolerance.
- **Breakout**: close above the base high (close-based, with buffer, per Skills 13/21/22).
- **Volume**: the classic VCP also requires volume to dry up through the contractions and expand on the breakout — not visible on this card face, but it is a core part of the original pattern and you already have this sensor from Skill 2. Include it as an optional filter and test its contribution.
- **Parameters to fix before testing**: minimum number of contractions (2 or 3), contraction ratio, maximum base length, maximum depth of the first pullback.

### Futures Adaptability Assessment (Skill 29)

**Verdict: mechanically codable and the risk profile is genuinely attractive — but be aware this pattern was developed for individual equities, and the rationale doesn't transfer cleanly to index futures.**

Why the origin matters:
- VCP describes supply absorption in a single stock: a finite float, identifiable institutional accumulation, and sellers being exhausted. Index futures have effectively unlimited contract creation and no float to absorb, so the "supply drying up" story doesn't apply the same way.
- The pattern may still work on futures as pure price geometry — tightening ranges before expansion is a real phenomenon (Skills 2 and 10 rely on it). But it would be working for a different reason than the theory claims, so validate it on futures data rather than importing equity results.
- If you trade individual equities or equity ETFs anywhere in the operation, VCP is much more at home there.

Practical notes if built for futures:
1. **Timeframe**: a daily/4H swing pattern. Compressing it to intraday produces noise — three "contractions" on a 5-min chart is often just chop.
2. **Best risk profile in the deck.** Entry sits directly above the shallowest contraction, so the structural stop is unusually tight relative to the potential move. Worth measuring: expected R:R here should be materially better than Skills 10 or 12.
3. **Overlap and consolidation.** This is now the third compression-breakout variant: Skill 2 (volume), Skill 10 (BB width), Skill 29 (pullback depth). Build one compression module with three detectors and one shared breakout executor — the same consolidation logic recommended for the RSI family at Skill 27.
4. **Sample size caution.** Strict VCP criteria produce few signals. On a single futures instrument you may get too few occurrences for statistical confidence; test across several instruments and a long history, and resist loosening the criteria until it produces enough trades, which is how this pattern gets curve-fit.

---

## Skill 30: The Pullback Strategy

Breakout above a channel/trendline boundary, then entry on the pullback that holds it. Card 7.4.

⚠️ **INCOMPLETE — rules side not yet captured** (twentieth consecutive chart-only card).

### What the chart shows

Price trades inside a broad, gently declining channel marked by two trendlines. A large green candle breaks decisively above the upper boundary. Price then consolidates above the broken line rather than running immediately, drifts back toward it, and Entry is marked as price turns back up. Stoploss sits below the pullback low (which is above the broken trendline). Price then advances.

No target is marked.

### Inferred Rules (pending text confirmation)

**BUY**
1. Identify the channel/trendline resistance.
2. Price breaks and closes above it.
3. Wait for the pullback toward the broken line — do not chase the breakout candle.
4. Entry: on the hold and turn back up.
5. Stoploss: below the pullback low.
6. Target: unmarked — measured move (channel height) or a trailing exit.

The card shows no SELL panel; the mirror construction is the obvious inverse.

### Relationship to the rest of the playbook

This is structurally identical to **Skill 26** — break a level, wait, enter on the retest — with one difference: the level is a **diagonal trendline/channel boundary** rather than a horizontal pivot. That single difference is the whole implementation question, because diagonal levels are harder to define objectively than horizontal ones:

- A trendline needs two or more anchor points, and which swing points to connect is a judgment call (the same objection raised against Gann in Skill 14, though far less severe here since the line follows actual swing points rather than an arbitrary angle).
- Objective constructions exist: connect the last two confirmed pivot highs; or use a linear regression channel over N bars (recommended in Skill 14 as the automatable substitute); or use the Donchian upper band (Skill 17), which is a horizontal-stepped version of the same idea.

### Mechanical Definitions for Automation

- **Trendline**: last two confirmed pivot highs, extended forward — deterministic once the pivot parameters are fixed. Note the pivot confirmation lag (Skill 19) applies to the anchors, though not to the break itself.
- **Alternative (preferred for automation)**: linear regression channel upper bound over N bars — no anchor selection, fully reproducible.
- **Break**: close above the line, with buffer.
- **Retest window**: price returns within tolerance of the (now rising/falling) line within N bars; expire otherwise.
- **Hold confirmation**: close back on the favourable side — the same test reused across Skills 4, 15, 16, 21, 24, 26.
- **Stop**: below the retest low. **Target**: channel height projected, or hand off to the trailing-exit engine.

### Futures Adaptability Assessment (Skill 30)

**Verdict: sound and codable, but almost entirely redundant with Skill 26. Build it as a "diagonal level" provider for the existing breakout-retest module, not as a separate strategy.**

Notes:
1. **Everything except the level definition already exists.** The break logic, retest window, hold confirmation, stop placement and bracket handling are all shared with Skill 26. The marginal build is one function that emits a diagonal level.
2. **Horizontal vs. diagonal is worth testing, not assuming.** On futures, horizontal levels (pivots, session highs/lows, prior-day extremes) attract resting orders in a way diagonal lines do not — there is no order book at "the trendline." That argues for horizontal levels carrying more real information on ES/NQ. Test both providers through the same engine and let the data decide; this is a clean experiment because only one component changes.
3. **Prefer the regression channel** if you build the diagonal provider, for the reproducibility reasons in Skill 14.
4. **Priority**: low, and only after Skills 13/26 are running. It adds a level provider, not a new edge.

### Deck-wide note at Skill 30

The convergence is now very pronounced. Thirty cards reduce to roughly nine distinct trade archetypes:
1. Compression → breakout (2, 10, 29)
2. Level break → retest entry (26, 30)
3. Level break → immediate entry (13, 22)
4. Trend pullback continuation (1, 3, 17, 19, 20)
5. Mean reversion to a mean line (5, 6, 8, 25, 27, 28)
6. Fade at a statistical/structural extreme (4, 9, 16, 24)
7. Trend-follow with trailing exit (12, 17, 19)
8. Zone/sweep reaction (15, 21)
9. Regime/context classifiers (3, 11, 23, 24)
Plus two not recommended for automation (14, 18/20) and one signal-only (5).

The build list has not grown since Skill 13. Each new card is now mostly adding a *variant* to an existing archetype rather than a new system — which is a good sign that the architecture identified at Skill 22 is the right one.

---

## Skill 31: 3-Minute Scalp Using Parabolic SAR, RSI and Heiken Ashi

Trend-following scalp: SAR flip for direction, RSI 50-line for confirmation. Card 5.1, "Scalping" category. Chart settings: SAR(0.02, 0.02, 0.2) and RSI(14, close, SMA 14, 2). Timeframe: 3 minutes.

⚠️ **INCOMPLETE — rules side not yet captured** (twenty-first consecutive chart-only card).

⚠️ **Heiken Ashi appears in the title but the chart shows what look like standard candles.** Whether HA is meant for display only or as the signal source is a material question — see the caveat below.

### What the chart shows

**BUY panel:** SAR dots flip from above price to below it. Buy is marked shortly after, Stoploss at the SAR dot beneath price. RSI is circled crossing UP through the 50 line ("Above 50"). Target is marked far up the advance, near where SAR eventually flips back above.

**SELL panel:** SAR flips to above price, Sell marked below, Stoploss at the SAR dot overhead, RSI circled crossing DOWN through 50 ("Below 50"), Target far down where SAR flips back.

Note the RSI filter here is the conventional 50-line trend reading — which is the reading I flagged as "Reading B" for Skill 25. That makes a misprint on Skill 25's card more likely, since this card uses the standard convention explicitly.

### Inferred Rules (pending text confirmation)

**BUY**
1. 3-minute chart.
2. SAR flips bullish (dots move below price).
3. RSI(14) above 50.
4. Entry: on the flip with RSI confirming.
5. Stoploss: the current SAR dot.
6. Exit: SAR flips back / the card's marked target.

**SELL** — mirror.

### The Heiken Ashi caveat — important

If HA candles are the signal source rather than just the display, this needs care:

- **HA candles do not show real prices.** HA open is the average of the previous HA open and close; HA close is the average of the current bar's OHLC. Neither is a price the market actually traded at that moment.
- Consequently, "enter at the HA candle close" is not a fillable instruction. A backtest that fills at an HA price is filling at a synthetic number — the same class of error described for Renko in Skill 18, and it inflates results in the same way.
- **Correct handling:** use HA only for signal *smoothing* (colour change, body/wick conditions), and fill at the real bar's price. Any P&L calculation must use actual OHLC, never HA values.
- HA also delays reversal signals by design; on a 3-minute scalp that lag is a material cost, not a rounding error.

Resolve from the rules text whether HA is decorative or load-bearing.

### Futures Adaptability Assessment (Skill 31)

**Verdict: workable, but this is Skill 12 with Parabolic SAR substituted for Supertrend — and SAR is the weaker of the two on futures. Treat it as a variant to test, not a new system.**

Why SAR is the weaker choice:
- Parabolic SAR is a pure trend-follower with no volatility normalisation in the way Supertrend's ATR basis provides. It is notoriously whipsaw-prone in ranges, and a 3-minute index-futures chart is range-bound a large fraction of the session.
- Its acceleration factor (0.02 step, 0.2 max) means the stop tightens the longer a trend runs, which can eject positions early in extended moves — the opposite of what you want on the trend days that pay for the chop.
- The RSI-50 filter helps, but the same filter applied to Supertrend (Skill 12) generally gives a more stable stop path.

What ports cleanly:
- SAR and RSI are both standard and bar-close evaluable; nothing new in the stack.
- SAR-as-stop is a legitimate trailing mechanism and slots into the trailing-exit engine alongside Supertrend, Donchian mid and fractal.

Caveats for futures:
1. **3-minute timeframe with a SAR stop can produce a very tight initial risk** — sometimes tighter than normal noise. Enforce a minimum stop distance (e.g. ≥ 0.75 × ATR) or the bot will be stopped out by spread and jitter.
2. **Transaction costs dominate at this frequency.** Same arithmetic as Skills 6 and 7: compute expected move vs. round-trip cost before assuming an edge.
3. **Whipsaw guard is essential** — session windows, minimum EMA/ADX separation, or the CPR day-type gate (Skill 23) to sit out rotational sessions.
4. **Consolidation**: this is the fourth trailing-stop trend-follower (12, 17, 19, 31). Add SAR as a fourth provider to the trailing-exit engine and A/B all four; do not maintain four separate strategies.
5. **Priority**: low. Test as a SAR variant of Skill 12 once that is running.

---

## Skill 32: M & W Positional Trading Strategy Using RSI

Double-top ("M") and double-bottom ("W") patterns identified on the RSI itself rather than on price. Card 4.4. Chart settings: RSI(14, close, SMA 14, 2) with bands.

⚠️ **INCOMPLETE — rules side not yet captured** (twenty-second consecutive chart-only card).

### What the chart shows

**BUY panel:** A "W like structure" is circled on the RSI at the lower band — two RSI troughs with a peak between. Entry is marked on price at that point, with Stoploss just below the entry low. Target is higher, near where an "M like structure" is circled on the RSI at the upper band. A second "W like structure" is circled later at another RSI low.

**SELL panel:** An "M like structure" is circled on the RSI near the upper band. Sell is marked on price with Stoploss above the local high, and Target far lower.

The logic is symmetrical and clear from the annotations: **W on RSI (at lows) = buy; M on RSI (at highs) = sell.** The M structure also serves as the exit marker for longs.

### Inferred Rules (pending text confirmation)

**BUY**
1. RSI(14) in the lower region forms a W: trough, bounce, second trough, then breaks above the intervening peak.
2. Entry: on price at the W completion.
3. Stoploss: below the recent price low.
4. Target: the next M structure on RSI / a higher price level.

**SELL** — mirror with an M structure at the RSI highs.

### Mechanical Definitions for Automation

- **RSI pivots**: `ta.pivotlow` / `ta.pivothigh` applied to the RSI series with a fixed lookback/lookforward.
- **W (double bottom on RSI)**: two RSI pivot lows within N bars, second within a tolerance band of the first (e.g. within ±5 RSI points, or second ≥ first for a rising W), separated by a pivot high; confirmed when RSI closes above that intervening peak.
- **M**: mirror.
- **Location filter**: require the W to form below a threshold (e.g. RSI < 40) and the M above one (e.g. RSI > 60), otherwise every RSI wiggle mid-range qualifies. The card's circles are all near the bands, which supports this.
- **Confirmation-lag warning**: identical to Skills 19 and 28 — RSI pivots aren't confirmed until the lookforward bars close, so the earliest legal entry is the confirmation bar, not the second trough. Any backtest entering at the trough is looking ahead.
- **Neckline break as trigger** is the cleaner formulation: it happens in real time and doesn't depend on pivot confirmation of the second trough.

### Futures Adaptability Assessment (Skill 32)

**Verdict: codable and reasonably well specified for a chart-only card — the M/W-on-RSI construction is more concrete than most oscillator pattern strategies. But it is the sixth RSI mean-reversion variant, and it shares the entire caveat set of Skill 28.**

What ports cleanly:
- RSI is in the stack; pattern detection on a numeric series is standard.
- Position ("positional" per the card title) implies a swing timeframe, where the pivot-confirmation lag costs proportionally less than it does on the 1-min scalps. That is a genuine advantage over Skill 28.
- Structural price stop, so risk is defined even though the signal lives on the oscillator.

Caveats for futures:
1. **Use the neckline break as the trigger**, not the second trough. This makes the signal real-time and removes most of the lookahead risk.
2. **Trend persistence still bites.** An M on RSI during a strong uptrend is frequently just a pause. Location filter plus a regime gate, as with every fade strategy in this deck (4, 16, 27, 28).
3. **Tolerance parameters are the whole strategy.** How close the two troughs must be, the maximum separation, and the location threshold each change the signal set substantially. Fix them before testing and resist retuning until the equity curve looks good.
4. **Consolidation, again.** RSI mean-reversion variants now number six: 8 (VWAP filter), 16 (σ-bands), 25 (slow RSI), 27 (volume oscillator), 28 (divergence), 32 (M/W patterns). One module, six pluggable confirmation filters, one experiment comparing them on identical data. Building six strategies here would be the single largest wasted effort available in this playbook.
5. **Priority**: medium-low. Worth including in the filter comparison because the swing timeframe suits it, but not a standalone build.

---

## Skill 33+: (reserved for future strategies)
