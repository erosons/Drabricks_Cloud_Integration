# Your Trading Bot (Version 1) — Explained in Plain English

This is the same plan as your technical README, just written the way you'd explain
it to a friend. Nothing here changes the design — it only translates it.

---

## The one big idea

> **The bot that places orders is NOT what makes you money. The testing process that
> decides which strategies are ALLOWED to place orders is what makes you money.**

Think of it like a talent show. Anyone can walk on stage (any strategy can be *tried*),
but almost nobody gets a record deal (very few strategies get *real money*). The book
this design is based on (Kevin Davey's) says you typically have to test **100–200 ideas
to find ONE worth trading for real.** So the whole system is built to be a strict,
unemotional judge that throws most ideas in the bin.

Your 23 playbook strategies aren't "features to turn on." They're **23 contestants**,
and you should expect most of them to be eliminated.

---

## The two halves of the system

The bot is split into two separate worlds that share one database:

**1. The Research Lab (new in v1)**
This is where strategies are tested on old historical data, over and over, in
increasingly harsh conditions. Nothing here touches real money. Its job is to *reject*
things.

**2. The Live Trader (from v0, now upgraded)**
This is the part that actually connects to your broker (Tradovate) and places orders on
CME futures. Crucially: **it will only trade a strategy that the Research Lab has already
approved.** If a strategy hasn't earned its badge, the live trader flat-out refuses to
send its orders — even if you tried to force it on.

---

## The approval ladder (the heart of v1)

Every strategy has to climb a 6-step ladder before it can trade real money. Fail any
step and it's **retired** (killed off — but the failure is saved as useful data).

| Step | Plain-English question | What it has to prove |
|------|------------------------|----------------------|
| **Idea** | "Is this even a real, clear rule?" | The entry and exit must be 100% mechanical — no vague "use judgment" and no cheating indicators that repaint history. |
| **Quick test** | "Is it worth spending computer time on?" | A fast test on the last 1–2 years, using *realistic* (pessimistic) fills and real costs, shows it makes money. |
| **Walk-forward** | "Does it work on data it has never seen?" | Tuned on old data, then tested on newer 'unseen' data. It has to stay profitable on the unseen part. |
| **Monte Carlo** | "What are the realistic odds of disaster?" | Shuffle the trade order 2,500 times to see the range of outcomes. Reward must be at least 2× the worst drawdown, and the chance of blowing up must be under 10%. |
| **Incubation** | "Does it work on TODAY's live data (paper only)?" | Run it for 3–6 months on live market data but with fake money, to catch mistakes no historical test can. |
| **Live** | "Keep going, or quit?" | Once real, it's watched constantly. If it drops below a pre-agreed 'quit line,' it's retired automatically — no second-guessing. |

**One rule that matters a lot:** if a strategy fails a step, you are **not allowed** to
just loosen the rules and re-test until it passes. That's lying to yourself. It has to
start over from scratch as a brand-new entry, with its past failures on record.

---

## Why "pessimistic fills" keeps coming up

When testing on old data, it's tempting to assume your orders filled at the best
possible price. That's a fantasy that makes bad strategies look great.

So this system **always assumes the worst realistic fill:**
- Your limit order only fills if the price actually pushes *through* it, not just touches it.
- You never get to "buy at the exact bottom" or "sell at the exact top" of a bar.
- Costs and slippage are subtracted from every single trade.

The payoff: if a strategy still looks good under these harsh assumptions, then **real
life should only be a pleasant surprise, never a nasty one.**

---

## How much money to bet per trade (position sizing)

Instead of always trading a fixed number of contracts, v1 sizes bets as a fraction of
your account:

> **Contracts = (a small fraction) × (your account equity) ÷ (the worst loss the
> strategy has ever taken)** — always rounded down, and never above your hard cap.

The "small fraction" isn't guessed — it's chosen by the Monte Carlo simulation, picking
the value that gives the best reward-to-risk *without* breaking your drawdown limits.

Three safety rules baked in:
- **New strategies always start at just 1 contract** until they've proven themselves live.
- **Bet sizing can't save a bad strategy** — it can only ruin a good one if done greedily,
  so the system deliberately stays conservative.
- **No "doubling down after a loss" (martingale) is even possible** — the bet size depends
  only on your account balance, never on whether you just lost. (This is why your playbook
  rejected the martingale card.)

---

## Not putting all your eggs in one basket (diversification)

A weekly report checks whether your live strategies are actually different from each
other, or just secretly doing the same thing:

- It measures how correlated their daily profits are (both long-term and in recent
  months, because things that look independent can all crash together in a crisis).
- It checks whether combining them gives a *smoother* overall equity curve than any one
  alone.
- If a new strategy is too similar to one you already run, it's held back — it would add
  risk without adding real variety.
- Near-twins you already spotted (like Donchian-pullback vs Supertrend) are limited to
  **one per market**.
- There's a **portfolio-wide daily loss limit**: if the whole account loses too much in
  one day, everything flattens and stops for the day.

---

## Watching live strategies (are they still working?)

Once a strategy is live, two charts answer "is this still the thing we approved?":

1. **The big equity line** — showing the test period, the paper period, and the live
   period all together. If the live part suddenly bends away from the historical slope,
   that's your earliest warning sign.
2. **The expectation cone** — the live profit line plotted against the range of outcomes
   Monte Carlo predicted. If live results keep hugging the *bottom* edge of that range,
   the strategy is quietly behaving like a different (worse) system.

Every week, the system hands you a short checklist: Are results normal? Are the real
fills close to what we assumed? Any reason to stop? Any reason to change bet size? **You**
answer these — the bot doesn't act on them automatically...

...**except the quit line.** That one is automatic. It's set *before* going live, based on
the worst realistic drawdown. If live losses cross it, the strategy is retired at the next
market open, no debate, no same-day undo.

Every ~6 months there's also a "is there something better on the bench?" review — a live
but mediocre strategy can be swapped out for a better tested one, even if it's still making
money (though nothing gets benched in its first 6 months).

---

## The daily safety audit (reconciliation)

This exists because of a real horror story in the book: an order that *should* have been
cancelled quietly sat overnight, filled into a position nobody noticed, and wasn't caught
for over 30 hours.

To prevent that, the bot constantly cross-checks itself against the broker:

| What it checks | How often | What it does if something's wrong |
|----------------|-----------|-----------------------------------|
| Do the broker's open orders match what the bot thinks it has? | every 5 min | Cancel stray orders instantly, alert you |
| Does the broker's position match the bot's records? | every 5 min | If the bot thinks it's flat but the broker shows a position → close it, alert you |
| Do the broker's fills match the bot's log? | hourly + end of day | Recompute profit using the broker as the source of truth |
| Is real slippage worse than assumed? | every fill | Track it; if consistently worse, review the fill model |
| Does the daily broker statement match? | 5 PM daily | Any unexplained difference blocks the next day's trading until you okay it |

The motto: **"Automated trading is not unattended trading"** — so the *attending* is
itself automated.

---

## The stuff carried over from v0 (unchanged)

The live-trading safety machinery you already had still applies, and now the approval
ladder sits *behind* all of it:

- **Three safety switches** plus a "confirm live" gate — and even with all of them ON, a
  strategy still won't trade unless the approval ladder says it's live.
- **One separate process per market** so a crash in one can't take down the others.
- **News blackouts** around high-impact USD news (stops trading 15 min before/after).
- **Trading hours** 8 AM–4 PM ET, with a forced flatten at 3:55 PM no matter what.
- **Auto-flatten if the connection drops** (dead-man's switch).
- **Risk math done in ticks**, with per-market risk settings required (no lazy defaults).

---

## The control panel (`config/config.yaml`), knob by knob

If the bot were a car, `config.yaml` is the dashboard: the ignition, the clock, the
radio presets. Two things it deliberately does **not** contain: **money rules** (how
many contracts, where stops go, daily loss limits — those live per-market in
`products.yaml`, and the bot refuses to start if a market is missing them) and
**passwords** (those come from environment variables, never from a file you might
share). Here's what each part of the dashboard does:

**The ignition (`mode`).** Two switches combine into three positions, like a car with
a valet key. Both off = *rehearsal mode*: the bot announces "I would buy YM here" but
sends nothing anywhere (today's setting). First switch on = orders go to a **practice
account** with fake money. Both on = real money. You cannot reach real money by
flipping one switch by accident — it takes two deliberate moves, plus the approval
ladder still standing behind them.

**Business hours (`session`).** The bot works 8 AM to 4 PM New York time, and at
**3:55 PM it closes everything and goes home, no exceptions** — like a shopkeeper who
never sleeps in the store. Why it matters: futures trade overnight, and overnight is
where thin markets and margin surprises live. This bot simply refuses to be there.

**The news lookout (`news_guard`).** Every evening it reads a public calendar of
scheduled economic announcements and marks the big red ones. *Example: the Fed
announces interest rates at 2:00 PM Wednesday. From 1:45 to 2:15 the bot won't open
anything new and cancels any waiting entry orders — because in those minutes prices
can jump over your stop like it isn't there. A position already open is held, not
panic-sold.*

**The "which contract?" picker (`contract_resolver`).** "YM" isn't one thing — it's a
new contract every three months, like milk cartons with different expiry dates. Once
a day the bot checks the exchange's official numbers and trades whichever carton the
whole market is currently drinking from (highest volume). If its data goes stale for
two days, it refuses to trade rather than guess.

**The shared toolbox (`shared_services`).** Six tools every strategy borrows instead
of building badly for itself:

- a **map maker** that marks swing highs/lows and important price levels
  (yesterday's high, VWAP bands, floor pivots);
- a **weather reporter** (regime classifier) that declares "today is trending" or
  "today is choppy," so trend-chasers stay in bed on choppy days and dip-buyers stay
  in bed on trending ones;
- a **referee** (strategy router) — only ONE strategy may play per market at a time,
  and the referee picks it *before* anyone is allowed to look for a trade. Best
  regime fit wins; ties go to the higher-priority strategy; and it never swaps
  players mid-trade — whoever opened a position finishes it;
- the **stop-mover** (trailing exit engine) with the quadrant trail as default.
  *Example: buy YM at 40,000 risking $500, target 40,300. Price hits 40,075 → stop
  moves to break-even (you can no longer lose). 40,150 → stop locks +$375. 40,225 →
  locks +$750. 40,300 → done, +$1,500. The stop only ever climbs, never slides back.*
  Exactly one trail style may be switched on at a time — turning on two is a
  configuration error and the bot won't start;
- a **bouncer** (execution guards) that turns away any trade where the expected move
  wouldn't even cover twice the cost of getting in and out, or where the stop would
  risk more than $50.

**The contestant list (`strategies`).** All ~23 playbook strategies written down with
their exact recipes (so results are reproducible), each with an `enabled` on/off flag.
Today only one is on: `order_flow_scalp`, the engine carried over from the old kraken
bot. And remember — `enabled: true` only means "allowed to audition." The approval
ladder decides who actually trades.

**The fuse box (`risk_operations` + `monitoring`).** If the internet connection drops,
close everything immediately. If the whole account loses more than the daily
portfolio limit, close everything and stop for the day. Each market writes its own
log file and health dashboard.

*The one-line summary: `config.yaml` decides **when and how** the bot is allowed to
act; `products.yaml` decides **how much it may lose trying**; and the approval ladder
decides **who gets to act at all**.*

---

## The build order (roadmap)

The live-trading half (phases 1–8 from v0) gets built **first**, because the Research Lab
reuses the same strategy code and database. Then the new v1 pieces get added in order:
data storage → backtester → walk-forward → Monte Carlo → the gatekeeper → incubation →
sizing → the daily auditor → live monitoring dashboards → the diversification report.

**Suggested first real test:** take `order_flow_scalp`, which is currently "live by
default," and run it *backwards* through the ladder. It's exactly the kind of
never-properly-tested strategy this whole v1 system was built to catch.

---

## The one sentence to remember

> Build a strict, unemotional **judge** (the Research Lab) that assumes the worst, kills
> most ideas, sizes bets carefully, watches the survivors like a hawk, and never lets you
> talk it out of quitting a broken strategy — and keep that judge running forever, because
> no strategy works indefinitely and you'll always need fresh contestants on the bench.
