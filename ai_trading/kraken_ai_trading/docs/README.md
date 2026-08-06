# Kraken AI Order Flow Trading Bot

A multi-pair, fully-async spot trading bot for the [Kraken](https://www.kraken.com/) exchange.  
It combines **order flow analysis**, **EMA trend filtering**, and **V-bottom / V-top exhaustion detection** to place passive limit orders with a progressive trailing stop.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Component Map](#2-component-map)
3. [Data Flow Diagram](#3-data-flow-diagram)
4. [Signal Decision Tree](#4-signal-decision-tree)
5. [Directory Structure](#5-directory-structure)
6. [Module Reference](#6-module-reference)
7. [Configuration Reference](#7-configuration-reference)
8. [Per-Pair Configuration](#8-per-pair-configuration)
9. [Risk Management](#9-risk-management)
10. [Price Action Intelligence](#10-price-action-intelligence)
11. [Monitoring Stack](#11-monitoring-stack)
12. [Quick Start](#12-quick-start)
13. [Deployment](#13-deployment)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          launcher.py                                │
│                    (Multi-Pair Orchestrator)                        │
│                                                                     │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐          │
│   │  XRP Process │   │  ETH Process │   │ DOGE Process │          │
│   │  main.py     │   │  main.py     │   │  main.py     │          │
│   │  --env xrp   │   │  --env eth   │   │  --env doge  │          │
│   │  port :8001  │   │  port :8002  │   │  port :8003  │          │
│   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘          │
│          │                  │                   │                   │
│   ┌──────▼──────────────────▼───────────────────▼──────┐          │
│   │         logs/  (xrp.log, eth.log, doge.log)         │          │
│   └────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────┘
         │                    │                   │
         ▼                    ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Kraken Exchange APIs                            │
│                                                                     │
│   REST v0                          WebSocket v2                     │
│   api.kraken.com/0/private/        wss://ws.kraken.com/v2          │
│   ┌──────────────────┐             ┌─────────────────────────┐     │
│   │ GetBalance       │             │ Public Channels          │     │
│   │ GetWebSocketsToken│            │  book  (order book)      │     │
│   │ CancelAllOrdersAfter│          │  trade (taker trades)    │     │
│   │ CancelAllOrders  │             │  ticker                  │     │
│   └──────────────────┘             │  heartbeat               │     │
│                                    ├─────────────────────────┤     │
│                                    │ Auth Channels            │     │
│                                    │  executions (fills/ACKs) │     │
│                                    │  add_order               │     │
│                                    │  cancel_order            │     │
│                                    └─────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Monitoring Stack (optional)                       │
│                                                                     │
│   Bot /metrics       Prometheus          Grafana                    │
│   :8001 / :8002  →   :9090         →    :3000                      │
│   :8003              (5 s scrape)        (5 s auto-refresh)         │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Process-per-pair isolation** | One crash never kills other pairs; restart/tune one without touching others; no shared-state locking needed |
| **Staggered startup (3 s/pair)** | Kraken nonces must be monotonically increasing per API key — simultaneous starts cause `EAPI:Invalid nonce` |
| **WebSocket for order management** | Lower latency than REST; Kraken v2 WS supports `add_order`, `amend_order`, `cancel_order` directly |
| **REST only for bootstrap + DMS** | `GetWebSocketsToken` and `CancelAllOrdersAfter` are REST-only endpoints |
| **Passive limit orders** | Maker fees are lower than taker on Kraken; joining best bid/ask avoids post-only rejection |
| **Unified `executions` channel** | One channel delivers all account fills; each bot filters by its own symbol to avoid cross-pair pollution |

---

## 2. Component Map

```
src/
├── auth/
│   └── signer.py ─────────────── HMAC-SHA512 signing for REST API
│
├── client/
│   ├── rest.py ───────────────── Async REST client (bootstrap + DMS)
│   └── websocket.py ──────────── Auto-reconnect WebSocket v2 client
│
├── market_data/
│   ├── orderbook.py ──────────── Level-2 book (SortedDict bids/asks)
│   └── ticker.py ─────────────── Ticker snapshot storage
│
├── trading/
│   ├── signals.py ────────────── Signal enum: BUY / SELL / NEUTRAL
│   ├── orders.py ─────────────── Order model + WebSocket OrderManager
│   ├── position.py ───────────── Fill reconciliation + P&L tracking
│   ├── risk.py ───────────────── Progressive trailing SL/TP
│   ├── price_action.py ───────── EMA trend + V-bottom/V-top + re-test
│   └── order_flow.py ─────────── Flow analyzer + strategy (main loop)
│
└── utils/
    ├── logger.py ─────────────── Structured logging with [PAIR] prefix
    └── metrics.py ────────────── Prometheus gauges and counters
```

### Internal Dependency Graph

```
order_flow.py  (strategy engine — owns all event handlers)
    ├── orderbook.py       reads mid-price, spread, imbalance
    ├── orders.py          places / cancels limit & market orders
    ├── position.py        tracks qty, avg price, P&L
    ├── risk.py            checks SL/TP on every trade tick
    ├── price_action.py    gates signals: trend + exhaustion
    ├── signals.py         shared Signal enum
    └── metrics.py         updates Prometheus after each event
```

---

## 3. Data Flow Diagram

### 3.1 Market Data Flow (book updates → order placement)

```
Kraken WebSocket v2  (public)
         │  book snapshot / update
         ▼
┌────────────────────────────────────────────────────────┐
│  on_public(msg)  message router                        │
│                                                        │
│  channel="book" snapshot ──► orderbook.apply_snapshot()│
│  channel="book" update   ──► orderbook.apply_update()  │
│  channel="trade"         ──► strategy.on_trade()       │
│  channel="ticker"        ──► ticker_feed.update()      │
└────────────────────┬───────────────────────────────────┘
                     │  (book update only)
                     ▼
┌────────────────────────────────────────────────────────┐
│  OrderFlowStrategy.on_book_update()                    │
│                                                        │
│  1. mid = orderbook.mid_price()                        │
│     price_action.on_price_tick(mid)                    │
│     ├── update fast EMA, slow EMA                      │
│     ├── run spike detector state machine               │
│     └── check saved levels for re-test                 │
│                                                        │
│  2. spread_bps = orderbook.spread_bps()                │
│     └── SKIP if > MAX_SPREAD_BPS                       │
│                                                        │
│  3. flow = analyzer.analyze(orderbook)                 │
│     score = 0.6 × imbalance + 0.4 × trade_delta       │
│     └── SKIP if confidence < MIN_CONFIDENCE            │
│                                                        │
│  4. effective = _gate_signal(flow.signal)              │
│     └── (see Signal Decision Tree)                     │
│                                                        │
│  5. BUY  → _post_bid()   join best bid, limit order   │
│     SELL → _post_ask()   join best ask, limit order   │
└────────────────────────────────────────────────────────┘
```

### 3.2 Trade Tick Flow (SL/TP monitoring)

```
Kraken WebSocket v2  (public)
         │  trade message
         ▼
┌────────────────────────────────────────────────────────┐
│  OrderFlowStrategy.on_trade()                          │
│                                                        │
│  for each trade in msg.data:                           │
│    analyzer.add_trade(price, qty, side, ts)            │
│    └── updates rolling 50-trade window                 │
│                                                        │
│    position_tracker.update_mark_price(price)           │
│    └── updates unrealized PnL                          │
│                                                        │
│    if risk_manager.has_position():                     │
│      reason, exit_price = on_price_update(price)       │
│      if reason != "none":                              │
│        _exit_position(reason, price)                   │
│        ├── cancel any pending working order            │
│        └── place_market_order() to close position      │
└────────────────────────────────────────────────────────┘
```

### 3.3 Fill / Execution Flow

```
Kraken WebSocket v2  (authenticated)
         │  executions message
         ▼
┌────────────────────────────────────────────────────────┐
│  on_auth(msg)  message router                          │
│                                                        │
│  channel="executions" ──► strategy.on_execution(msg)  │
│  method="add_order" ACK ──► log order_id              │
│  method="add_order" NACK ──► strategy.on_order_nack() │
└────────────────────┬───────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────┐
│  OrderFlowStrategy.on_execution()                      │
│                                                        │
│  order_manager.on_execution(msg)                       │
│  └── update Order.status / filled_qty                  │
│                                                        │
│  for each exec_type="trade":                           │
│    skip if symbol != self.symbol  ◄── cross-pair guard │
│                                                        │
│    position_tracker.on_fill(side, qty, price, fee)     │
│    └── update avg_price, realized_pnl                  │
│                                                        │
│    if remaining_qty == 0:                              │
│      clear active order  → metrics.inc_orders_filled() │
│                                                        │
│    if new position opened:                             │
│      risk_manager.on_entry(entry, qty, side)           │
│      └── set sl_price, tp_price, trail levels          │
│                                                        │
│    metrics.update_position(qty, sl, tp)                │
│    metrics.update_pnl(realized, unrealized)            │
└────────────────────────────────────────────────────────┘
```

### 3.4 Dead-Man's Switch

```
Every DEAD_MANS_SWITCH_SECONDS (default: 60 s):
         │
         ▼
  REST: CancelAllOrdersAfter(timeout = 120 s)
  ├── If refreshed in time → orders stay open
  └── If bot dies → Kraken auto-cancels everything after 120 s

On SIGINT / SIGTERM:
  ├── REST: cancel_all_orders()     (immediate)
  ├── pub_ws.disconnect()
  └── auth_ws.disconnect()
```

---

## 4. Signal Decision Tree

Every book update passes through two layers before any order is placed.

```
Book Update Received
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  Gate 0: Pre-checks                                 │
│                                                     │
│  spread > MAX_SPREAD_BPS?  ──────────────────► SKIP │
│  nack_pause active?        ──────────────────► SKIP │
│  within 10 s of last order?──────────────────► SKIP │
│  order_lock held?          ──────────────────► SKIP │
└──────────────────────────┬──────────────────────────┘
                           │ pass
                           ▼
┌─────────────────────────────────────────────────────┐
│  Layer 1: Order Flow Analysis                       │
│                                                     │
│  imbalance   = (bid_vol − ask_vol) / total_vol      │
│  trade_delta = (buy_vol − sell_vol) / total_vol     │
│  score       = 0.6 × imbalance + 0.4 × trade_delta │
│                                                     │
│  score >  THRESHOLD → BUY signal                   │
│  score < −THRESHOLD → SELL signal                  │
│  else               → NEUTRAL                      │
│                                                     │
│  confidence = |score| / THRESHOLD                  │
│  confidence < MIN_CONFIDENCE  ───────────────► SKIP │
└──────────────────────────┬──────────────────────────┘
                           │ flow signal
                           ▼
┌─────────────────────────────────────────────────────┐
│  Layer 2: Price Action Gate (_gate_signal)           │
│                                                     │
│  ┌─ Exhaustion active? (V-bottom, V-top, re-test)   │
│  │                                                  │
│  │  YES:  exhaustion == flow? → PASS (reversal)     │
│  │        exhaustion != flow? → SKIP (conflict)     │
│  │                                                  │
│  └─ NO:   EMA trend == flow? → PASS (continuation) │
│           EMA trend != flow? → SKIP (against trend) │
└──────────────────────────┬──────────────────────────┘
                           │ PASS
                    ┌──────┴──────┐
                  BUY           SELL
                    │             │
             pos < MAX_POS   pos > 0
                    │             │
              _post_bid()   _post_ask()
           (join best bid) (join best ask)
```

### Price Action State Machine

```
                    ┌────────────────────────────────────┐
                    │              IDLE                  │
                    │    exhaustion = NEUTRAL            │
                    └─────────────┬──────────────────────┘
                                  │
              ┌───────────────────┼──────────────────────┐
              │                   │                      │
      price drops            (tick count               price rises
      > SPIKE_THRESHOLD      < SLOW_EMA                > SPIKE_THRESHOLD
      from slow EMA          → no signals)             from slow EMA
              │                                          │
              ▼                                          ▼
    ┌─────────────────┐                      ┌─────────────────┐
    │   SPIKE_DOWN    │                      │    SPIKE_UP     │
    │  track lowest   │                      │  track highest  │
    └────────┬────────┘                      └────────┬────────┘
             │                                        │
   recovery ≥ RECOVERY_PCT               rejection ≥ RECOVERY_PCT
             │                                        │
             ▼                                        ▼
    ┌─────────────────┐                      ┌─────────────────┐
    │   V-BOTTOM ✓    │                      │    V-TOP ✓      │
    │ exhaustion=BUY  │                      │ exhaustion=SELL │
    │ TTL=60 ticks    │                      │ TTL=60 ticks    │
    │ save support    │                      │ save resistance │
    │ level in memory │                      │ level in memory │
    └────────┬────────┘                      └────────┬────────┘
             │                                        │
             └──────────────► IDLE ◄──────────────────┘
                            (TTL counting down)
                                  │
                   Price returns within RETEST_PROXIMITY
                   of saved level while exhaustion=NEUTRAL
                                  │
                                  ▼
                    ┌────────────────────────────────────┐
                    │    RE-TEST signal fires             │
                    │  exhaustion = saved direction       │
                    │  TTL = RETEST_TTL (shorter)         │
                    └────────────────────────────────────┘
```

---

## 5. Directory Structure

```
kraken_ai_trading/
│
├── launcher.py              # Multi-pair orchestrator — spawn/restart/aggregate logs
├── main.py                  # Single-pair entrypoint — bootstrap & async event loop
├── pyproject.toml           # Packaging, dependencies, tool config
│
├── pairs/                   # Per-pair environment files
│   ├── btc.env              # BTC/USD  — DRY_RUN=true (simulation)
│   ├── eth.env              # ETH/USD  — DRY_RUN=false (live) METRICS_PORT=8002
│   ├── xrp.env              # XRP/USD  — DRY_RUN=false (live) METRICS_PORT=8001
│   └── doge.env             # DOGE/USD — DRY_RUN=false (live) METRICS_PORT=8003
│
├── src/
│   ├── auth/
│   │   └── signer.py        # HMAC-SHA512 signing + nonce generation
│   ├── client/
│   │   ├── rest.py          # Async REST client (Kraken v0 API)
│   │   └── websocket.py     # Auto-reconnect WebSocket v2 client
│   ├── market_data/
│   │   ├── orderbook.py     # Level-2 order book with CRC32 checksum validation
│   │   └── ticker.py        # Ticker snapshot + feed manager
│   ├── trading/
│   │   ├── signals.py       # Signal enum: BUY / SELL / NEUTRAL
│   │   ├── orders.py        # Order model + WebSocket OrderManager
│   │   ├── position.py      # Fill tracking + P&L calculation
│   │   ├── risk.py          # Progressive trailing stop / take-profit
│   │   ├── price_action.py  # EMA trend + V-bottom/V-top + re-test detector
│   │   └── order_flow.py    # Order flow analyzer + strategy (central event hub)
│   └── utils/
│       ├── logger.py        # Structured logging with [PAIR] tag
│       └── metrics.py       # Prometheus client (14 metrics per pair)
│
├── monitoring/
│   ├── prometheus.yml       # Scrape config — targets :8001/:8002/:8003 every 5 s
│   ├── start_monitoring.sh  # One-command launcher for Prometheus + Grafana
│   └── grafana/
│       ├── provisioning/
│       │   ├── datasources/ # Prometheus datasource auto-wiring
│       │   └── dashboards/  # Dashboard file provider config
│       └── dashboards/
│           └── kraken_bot.json  # Pre-built dashboard (9 panels)
│
└── logs/                    # Auto-created; one rotating file per pair
    ├── xrp.log
    ├── eth.log
    └── doge.log
```

---

## 6. Module Reference

### `src/auth/signer.py`

Kraken private REST endpoints require HMAC-SHA512 authentication:

```
Signature = HMAC-SHA512(
  key = base64_decode(api_secret),
  msg = url_path + SHA256(nonce + POST_body)
)
```

**Nonce**: microsecond timestamp (`int(time.time() × 1_000_000)`).  
Nonces must strictly increase per API key — the 3-second stagger between pair processes prevents collisions on restart.

---

### `src/client/websocket.py`

| Endpoint | URL |
|----------|-----|
| Public | `wss://ws.kraken.com/v2` |
| Authenticated | `wss://ws-auth.kraken.com/v2` |

**Auto-reconnect backoff**: 1 s → 2 s → 4 s → … → 60 s cap.  
**Subscription replay**: all active subscriptions are re-sent automatically after reconnect.

---

### `src/market_data/orderbook.py`

Uses `SortedDict` for O(log n) insert/remove on both bids and asks.

```
Imbalance = (bid_vol_N − ask_vol_N) / (bid_vol_N + ask_vol_N)
  +1.0 → all volume on bids  (strong buy pressure)
  −1.0 → all volume on asks  (strong sell pressure)

Spread BPS = (best_ask − best_bid) / mid_price × 10,000
```

---

### `src/trading/order_flow.py`

Central event hub. All WebSocket messages route here.

```
on_book_update()   Called on every book tick — main signal + order logic
on_trade()         Called on every public trade — feeds analyzer, checks SL/TP
on_execution()     Called on every fill — reconciles position, registers risk
on_order_nack()    Called on rejection — backoff logic for insufficient-funds
```

**Order cooldown**: 10 seconds minimum between any two order events.  
**NACK backoff**: 3 consecutive "Insufficient funds" → 60-second pause on order submission.

---

### `src/trading/risk.py`

```
Entry: symbol=XRP/USD  entry=$1.3521  qty=70  STOP_LOSS_USD=$5  RR=3.0

  sl_per_unit = 5.00 / 70      = $0.0714/XRP
  tp_per_unit = 15.00 / 70     = $0.2143/XRP
  trail_step  = 0.2143 × 0.25  = $0.0536/XRP

  Initial:       SL=$1.2807  (entry − sl_per_unit)
  Milestone 1:   SL=$1.3521  (break-even, at price $1.4057)
  Milestone 2:   SL=$1.4057  (trailing, at price $1.4593)
  Milestone 3:   SL=$1.4593  ...
```

SL advances only forward — it never retreats toward the entry.

---

### `src/utils/metrics.py`

| Metric | Type | Label |
|--------|------|-------|
| `bot_fast_ema` | Gauge | pair |
| `bot_slow_ema` | Gauge | pair |
| `bot_mid_price` | Gauge | pair |
| `bot_signal` | Gauge | pair (1=BUY, 0=NEUTRAL, −1=SELL) |
| `bot_exhaustion_active` | Gauge | pair |
| `bot_position_qty` | Gauge | pair |
| `bot_sl_price` | Gauge | pair |
| `bot_tp_price` | Gauge | pair |
| `bot_unrealized_pnl_usd` | Gauge | pair |
| `bot_realized_pnl_usd` | Gauge | pair |
| `bot_orders_placed_total` | Counter | pair |
| `bot_orders_filled_total` | Counter | pair |
| `bot_orders_cancelled_total` | Counter | pair |
| `bot_sl_hits_total` | Counter | pair |
| `bot_tp_hits_total` | Counter | pair |

---

## 7. Configuration Reference

Every setting is an environment variable loaded from `pairs/<pair>.env` via `python main.py --env pairs/<pair>.env`.

### Credentials

| Env Var | Required | Description |
|---------|----------|-------------|
| `KRAKEN_API_KEY` | ✅ | API key from Kraken account settings |
| `KRAKEN_API_SECRET` | ✅ | API secret (base64-encoded) |

> **Security**: API key should have **Trade + Query** permissions only. Never enable **Withdrawal**.

### Trading

| Env Var | Default | Description |
|---------|---------|-------------|
| `TRADING_PAIR` | `BTC/USD` | Symbol in Kraken format (e.g. `XRP/USD`, `ETH/USD`) |
| `ORDER_SIZE` | `0.001` | Base asset quantity per limit order |
| `MAX_POSITION` | `0.01` | Maximum base asset to hold simultaneously |
| `BOOK_DEPTH` | `25` | Order book levels to subscribe (1–500) |
| `PRICE_DECIMALS` | `1` | Decimal places for price rounding when posting orders |
| `DRY_RUN` | `true` | `false` = live trading; `true` = simulate (no orders submitted) |

### Signal Thresholds

| Env Var | Default | Description |
|---------|---------|-------------|
| `IMBALANCE_THRESHOLD` | `0.25` | Minimum combined flow score to generate a signal |
| `MIN_CONFIDENCE` | `0.55` | Minimum signal confidence (0–1) |
| `MAX_SPREAD_BPS` | `15.0` | Skip if spread exceeds this (basis points; 100 = 1%) |

### Risk Management

| Env Var | Default | Description |
|---------|---------|-------------|
| `STOP_LOSS_USD` | `30.0` | Maximum dollar loss per position |
| `RISK_REWARD_RATIO` | `3.0` | Take-profit = stop-loss × ratio |
| `TRAIL_STEP_PCT` | `0.25` | Trail step as fraction of total TP range |

### Price Action

| Env Var | Default | Description |
|---------|---------|-------------|
| `FAST_EMA` | `20` | Fast EMA period (book-update ticks) |
| `SLOW_EMA` | `60` | Slow EMA period; also controls warmup — no signals until this many ticks received |
| `SPIKE_THRESHOLD` | `0.003` | Min % deviation from slow EMA to start tracking a spike |
| `RECOVERY_PCT` | `0.5` | Fraction of spike that must reverse to confirm V-bottom/V-top |
| `EXTREME_WINDOW` | `200` | Ticks to track rolling high/low |
| `EXHAUSTION_TTL` | `60` | Ticks the V-bottom/V-top signal stays active |

### Support/Resistance Re-Test

| Env Var | Default | Description |
|---------|---------|-------------|
| `RETEST_PROXIMITY` | `0.002` | Within 0.2% of a confirmed level = re-test trigger |
| `RETEST_MEMORY_TICKS` | `400` | Ticks to remember a V-bottom/V-top level |
| `RETEST_TTL` | `40` | Exhaustion signal TTL for a re-test (shorter than initial) |

### Infrastructure

| Env Var | Default | Description |
|---------|---------|-------------|
| `DEAD_MANS_SWITCH_SECONDS` | `60` | REST heartbeat interval; Kraken auto-cancels at 2× this |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `METRICS_PORT` | `0` | Prometheus HTTP port (0 = disabled) |

---

## 8. Per-Pair Configuration

Each pair is tuned for its price level, volatility, and liquidity characteristics.

### XRP/USD (`pairs/xrp.env`)

| Setting | Value | Rationale |
|---------|-------|-----------|
| `ORDER_SIZE` | 30 | ~$40 per order |
| `MAX_POSITION` | 70 | ~$94 max exposure |
| `PRICE_DECIMALS` | 4 | XRP trades to 4 decimal places |
| `MAX_SPREAD_BPS` | 15 | Moderate liquidity |
| `FAST_EMA` | 20 | Standard — smooth price action |
| `SLOW_EMA` | 60 | Standard trend window |
| `SPIKE_THRESHOLD` | 0.003 | 0.3% — moderate volatility |
| `RETEST_PROXIMITY` | 0.002 | 0.2% — tight; XRP levels are clean |
| `METRICS_PORT` | 8001 | Prometheus endpoint |

### ETH/USD (`pairs/eth.env`)

| Setting | Value | Rationale |
|---------|-------|-----------|
| `ORDER_SIZE` | 0.005 | ~$10 per order |
| `MAX_POSITION` | 0.05 | ~$105 max exposure |
| `PRICE_DECIMALS` | 2 | ETH trades to 2 decimal places |
| `MAX_SPREAD_BPS` | 12 | Very liquid; tight spread tolerance |
| `FAST_EMA` | 20 | Standard |
| `SLOW_EMA` | 60 | Standard |
| `SPIKE_THRESHOLD` | 0.002 | 0.2% — ETH less volatile than DOGE |
| `RETEST_PROXIMITY` | 0.002 | 0.2% — tight |
| `METRICS_PORT` | 8002 | Prometheus endpoint |

### DOGE/USD (`pairs/doge.env`)

| Setting | Value | Rationale |
|---------|-------|-----------|
| `ORDER_SIZE` | 50 | ~$5 per order |
| `MAX_POSITION` | 500 | ~$51 max exposure |
| `PRICE_DECIMALS` | 5 | DOGE trades to 5 decimal places |
| `MAX_SPREAD_BPS` | 20 | Wider — DOGE spreads are noisier |
| `FAST_EMA` | 15 | Shorter — DOGE moves fast |
| `SLOW_EMA` | 50 | Shorter trend window |
| `SPIKE_THRESHOLD` | 0.005 | 0.5% — high volatility |
| `RETEST_PROXIMITY` | 0.004 | 0.4% — wider for spread noise |
| `METRICS_PORT` | 8003 | Prometheus endpoint |

### BTC/USD (`pairs/btc.env`)

| Setting | Value | Rationale |
|---------|-------|-----------|
| `ORDER_SIZE` | 0.0001 | ~$10 per order |
| `MAX_POSITION` | 0.001 | ~$105 max exposure |
| `PRICE_DECIMALS` | 1 | BTC trades to 1 decimal place |
| `MAX_SPREAD_BPS` | 10 | Most liquid — tightest filter |
| `DRY_RUN` | true | Simulation only |

---

## 9. Risk Management

### SL/TP Calculation

```
stop_loss_per_unit  = STOP_LOSS_USD / MAX_POSITION
take_profit_per_unit = STOP_LOSS_USD × RISK_REWARD_RATIO / MAX_POSITION

Long position:
  sl_price = entry − stop_loss_per_unit
  tp_price = entry + take_profit_per_unit

Short position:
  sl_price = entry + stop_loss_per_unit
  tp_price = entry − take_profit_per_unit
```

`MAX_POSITION` (not the actual fill quantity) is used for sizing — so the first partial fill does not create an oversized stop.

### Trailing Stop Progression

```
trail_step = (tp_price − sl_price) × TRAIL_STEP_PCT

Milestone 0 → 1  price ≥ entry + trail_step   SL → entry (break-even)
Milestone 1 → 2  price ≥ sl + 2 × trail_step  SL → sl + trail_step
Milestone N → +1 price ≥ sl + 2 × trail_step  SL → sl + trail_step
```

SL only ever advances toward TP — it never retreats.

### Dead-Man's Switch

```
Every 60 s:  REST CancelAllOrdersAfter(120 s)
             └── Kraken holds a timer; refresh keeps orders alive
             └── If bot stops for any reason, orders auto-cancel after 120 s

On SIGINT/SIGTERM:
             └── Immediate REST cancel_all_orders()
             └── WebSocket disconnect
```

---

## 10. Price Action Intelligence

### EMA Trend Filter

```
alpha_fast = 2 / (FAST_EMA + 1)
alpha_slow = 2 / (SLOW_EMA + 1)

EMA_t = alpha × price_t + (1 − alpha) × EMA_{t-1}

trend = UP      when (fast − slow) / slow >  +TREND_MIN_DIFF (0.05%)
trend = DOWN    when (fast − slow) / slow <  −TREND_MIN_DIFF
trend = NEUTRAL during warmup OR flat market
```

**Warmup**: No signals generated until `SLOW_EMA` ticks received (typically 2–5 minutes of book activity).

### V-Bottom / V-Top Detection

Catches sharp capitulation moves and reversal patterns:

```
V-Bottom:
  1. price drops > SPIKE_THRESHOLD% below slow EMA
     → SPIKE_DOWN: start tracking lowest price
  2. price recovers RECOVERY_PCT × drop from the low
     → confirmed: emit exhaustion=BUY for EXHAUSTION_TTL ticks
     → save support level in level_memory

V-Top (mirror):
  1. price rises > SPIKE_THRESHOLD% above slow EMA → SPIKE_UP
  2. price rejects RECOVERY_PCT × rise → confirmed
     → emit exhaustion=SELL for EXHAUSTION_TTL ticks
     → save resistance level in level_memory
```

### Support / Resistance Re-Test

When price returns to a previously confirmed level:

```
Every tick, for each saved level:
  proximity = |price − level| / level

  if proximity ≤ RETEST_PROXIMITY AND exhaustion == NEUTRAL:
    re-arm exhaustion in saved direction
    TTL = RETEST_TTL  (shorter than initial)
    log → "RE-TEST support level=X.XXXX price=Y.YYYY"

Level expires after RETEST_MEMORY_TICKS ticks.
```

### Gate Truth Table

| Flow | Exhaustion | EMA Trend | Decision |
|------|------------|-----------|----------|
| BUY | BUY | any | ✅ BUY — reversal entry |
| SELL | SELL | any | ✅ SELL — reversal entry |
| BUY | NEUTRAL | UP | ✅ BUY — trend continuation |
| SELL | NEUTRAL | DOWN | ✅ SELL — trend continuation |
| BUY | SELL | any | ❌ SKIP — signal conflict |
| SELL | BUY | any | ❌ SKIP — signal conflict |
| BUY | NEUTRAL | DOWN | ❌ SKIP — against trend |
| SELL | NEUTRAL | UP | ❌ SKIP — against trend |
| any | NEUTRAL | NEUTRAL | ❌ SKIP — warmup / flat |

---

## 11. Monitoring Stack

### Stack Overview

```
Bot processes                  Prometheus            Grafana
(main.py × 3)                  (TSDB)               (dashboard)

XRP  :8001/metrics ──────┐
ETH  :8002/metrics ──────┼──► :9090 ───────────► :3000
DOGE :8003/metrics ──────┘   (5 s scrape)        (5 s refresh)
```

### Starting the Stack

```bash
bash monitoring/start_monitoring.sh
```

Outputs:
```
 Dashboard  →  http://localhost:3000   (admin / admin)
 Metrics    →  http://localhost:9090
 Bot feeds  →  :8001 (XRP)  :8002 (ETH)  :8003 (DOGE)
```

### Dashboard Panels

| Panel | Type | What It Shows |
|-------|------|---------------|
| EMA — Fast vs Slow | Time series | fast_ema (green), slow_ema (blue), mid_price (yellow dashed) |
| Signal | Stat | BUY / NEUTRAL / SELL with color background |
| Exhaustion Active | Stat | REVERSAL / none |
| Position Size | Stat | Current base-asset quantity held |
| Stop-Loss Price | Stat (red) | Current SL level in USD |
| Take-Profit Price | Stat (green) | Current TP level in USD |
| Unrealized PnL | Stat (threshold) | Green when positive, red when negative |
| Realized PnL | Time series | Cumulative session profit |
| Order Activity | Time series | Placed/min, Filled/min, SL hits/5m, TP hits/5m |

Use the **`pair` dropdown** to switch between XRP, ETH, and DOGE.

### Useful PromQL Queries

```promql
# Live mid prices all pairs
bot_mid_price

# EMA spread (positive = uptrend)
bot_fast_ema{pair="XRP/USD"} - bot_slow_ema{pair="XRP/USD"}

# Fill rate (filled / placed)
rate(bot_orders_filled_total[5m]) / rate(bot_orders_placed_total[5m])

# Win rate (TP exits / total exits)
rate(bot_tp_hits_total[1h]) /
  (rate(bot_tp_hits_total[1h]) + rate(bot_sl_hits_total[1h]))

# Combined session P&L across all pairs
sum(bot_realized_pnl_usd)
```

---

## 12. Quick Start

### Prerequisites

```bash
python3 --version   # requires 3.11+
pip install -e .    # installs all dependencies from pyproject.toml
```

### Credentials

```bash
# Edit your pair env files — never commit these
nano pairs/xrp.env
#  KRAKEN_API_KEY=<your key>
#  KRAKEN_API_SECRET=<your secret>
```

### Dry Run (Simulation)

```bash
# Single pair — no orders submitted
DRY_RUN=true python main.py --env pairs/xrp.env

# All pairs in simulation
python launcher.py xrp eth doge --dry-run
```

In dry-run mode: orders are validated but not submitted; dead-man's switch is disabled; all signals and P&L calculations run normally.

### Live Trading

```bash
# Confirm DRY_RUN=false in your .env files, then:
python launcher.py xrp eth doge
```

### Pair Management

```bash
python launcher.py --list          # show available pairs
python launcher.py xrp             # run only XRP
python launcher.py xrp eth         # run XRP and ETH
python main.py --env pairs/xrp.env # run one pair directly (debug)
```

---

## 13. Deployment

### systemd (Recommended for Production)

```ini
# /etc/systemd/system/kraken-bot.service
[Unit]
Description=Kraken AI Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<your-user>
WorkingDirectory=/path/to/kraken_ai_trading
ExecStart=/usr/bin/python3 launcher.py xrp eth doge
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable kraken-bot
sudo systemctl start kraken-bot
sudo journalctl -u kraken-bot -f
```

### tmux (Quick / Development)

```bash
tmux new -s trading
python launcher.py xrp eth doge
# Ctrl+B, D  (detach — session keeps running)
tmux attach -t trading
```

### Log Tailing

```bash
tail -f logs/xrp.log               # single pair
tail -f logs/*.log                  # all pairs
frontail logs/xrp.log logs/eth.log  # browser UI at :9001
```

### Installing Monitoring Binaries

```bash
# Grafana (Ubuntu / Debian)
sudo apt-get install -y grafana

# Prometheus
PROM=3.4.0
wget https://github.com/prometheus/prometheus/releases/download/v${PROM}/prometheus-${PROM}.linux-amd64.tar.gz
tar xzf prometheus-${PROM}.linux-amd64.tar.gz
sudo cp prometheus-${PROM}.linux-amd64/prometheus /usr/local/bin/

# Start both
bash monitoring/start_monitoring.sh
```

### Pre-Live Checklist

- [ ] `DRY_RUN=false` set intentionally in target pair `.env`
- [ ] `STOP_LOSS_USD` is a dollar amount you accept losing
- [ ] `ORDER_SIZE` and `MAX_POSITION` match your capital allocation
- [ ] API key has **Trade + Query** only — no Withdrawal permission
- [ ] Logs show `Dead-man's switch refreshed (120s)` every 60 seconds
- [ ] Ran at least one session in `DRY_RUN=true` to validate signal logic
- [ ] Grafana dashboard is live and updating before going live

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `aiohttp` | ≥3.9 | Async HTTP for Kraken REST API |
| `websockets` | ≥12.0 | Kraken WebSocket v2 connection |
| `python-dotenv` | ≥1.0 | Load per-pair `.env` configuration |
| `sortedcontainers` | ≥2.4 | `SortedDict` for order book bids/asks |
| `prometheus_client` | ≥0.20 | Expose bot metrics for Grafana |
| `anthropic` | ≥0.40 | Claude API (reserved for future AI features) |

---

*Python 3.11+ · Kraken WebSocket API v2 · Prometheus + Grafana*


python close_position.py SAND 0.0521          # sell all SAND at 0.0521
python close_position.py XRP 2.10             # sell all XRP at 2.10
python close_position.py BTC 115000 --qty 0.0004   # partial BTC position
python close_position.py ETH 3600 --side buy  # buy to close a short
python close_position.py SAND 0.0521 --dry-run     # preview, no order
python close_position.py SAND 0.0521 --yes    # skip the y/N prompt