# Changelog

All notable changes to the Tradovate CME futures bot are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (research plane)

- **Tick backtester** (`src/research/backtester.py`, §9) — replays Databento
  TBBO history through the SAME engine/risk/session code as live, with the
  pessimistic fill model: limit fills only on penetration (touches counted,
  never filled), stops fill at the worse of stop/trade price minus slippage,
  TP/flatten exits fill next tick with adverse slippage, commissions per
  side. Sim time drives both engine clocks — new `clock_fn` injection point
  in `FuturesOrderFlowStrategy` (live default unchanged: `time.monotonic`)
  so the 10s cooldown / 60s NACK pause elapse in market time. News guard is
  permissive (no historical calendar) and says so in `fill_flags`. Results
  persist to `backtest_runs` + per-trade CSV. `scripts/backtest.py` CLI
  **enforces the holdout**: runs reaching ≥ 2026-05-20 are refused without
  `--holdout`. 16 tests (166 total). Verified on real data: 2025-09-03
  MES day = 273,907 ticks in ~40s (≈7k ticks/s; full 9-month dev set ≈ 2h).

### Changed

- **Market data source: Tradovate → Databento** (2026-08-21). Tradovate support
  confirmed `md/subscribe*` requires a CME ILA sub-vendor license (not available
  to retail keys), so live market data now streams from Databento GLBX.MDP3
  (Standard plan, trades + mbp-1, raw CME symbols). New
  **`DatabentoFeed`** (`src/market_data/databento_feed.py`) replaces the
  Tradovate MD socket in `main.py`'s `_md_loop`: same drop-and-resync
  semantics, native aggressor side from `TradeMsg` (the best-ask inference
  survives only as the `side == 'N'` fallback), DBN int64 prices rounded to
  exact tick multiples (epsilon artifact caught live: `7670250000000 * 1e-9 ==
  7670.250000000001`). DRY_RUN mode no longer touches Tradovate at all — it
  needs only `DATABENTO_API_KEY`. `book_depth` drops 10 → 1 (Standard live is
  L1-only; depth-10 imbalance is a backtest question on the pulled MBP-10
  month). Tradovate keeps orders + fills; `MdRouter` remains for reference.
- **`scripts/check_live_feed.py`**: read-only soak probe for the Databento
  feed through the bot's own translation path, with optional raw-record
  capture. **Verified live 2026-08-21**: MESU6 mapped, ~1,400 records/20s,
  book synced at one-tick spread, both aggressor sides observed; full
  dry-run pipeline ran on live data and the session gate + SIGINT shutdown
  behaved correctly.
- **`scripts/fetch_history.py`**: Databento batch downloader (refuses any
  pull the subscription doesn't cover at $0). Pulled at $0: 1yr TBBO +
  1mo MBP-10 for MES.v.0 and MNQ.v.0 (~36 GB, git-ignored `data/databento/`).
- 12 offline `DatabentoFeed` tests with real DBN record objects (139 total).
- **`docs/README.md` architecture updated for the broker/data split**: §1
  diagram (Databento live-MD box; gateway is orders + fills only; MD off the
  Tradovate rate budget), Key Design Decisions (new "Tradovate executes,
  Databento feeds" row), §9 data source (Databento TBBO/MBP-10 pulls), §17
  CME-ILA note + attestation rows 24–25/31, §18 component map
  (`databento_feed.py`; `stream.py` marked reference-only), §19 (`scripts/`,
  `data/databento/`), §21 (`databento` config block).

### Added

- **Trade-success monitoring** (2026-08-21): win/loss/rejection tracking with
  two labeled sources and one authority (README §15). New Prometheus counters
  `bot_trades_won_total` / `bot_trades_lost_total` (classified by realized P&L
  net of fees at round-trip close — NOT sl/tp hits, which misclassify
  profitable trailed-stop exits) and `bot_orders_rejected_total` (order
  NACKs). New **`v_round_trips` SQL view** reconstructs round trips from the
  `fills` table (trip = flat→flat, win = `usd_pnl >= 0`) — the of-record
  source that survives restarts. **Fills now actually persist**: `main.py`'s
  fill handler writes every broker fill via `db.record_fill` (previously
  defined but never called — the live path recorded nothing). New Grafana
  stack under `monitoring/`: `docker-compose.yml` (Prometheus + Grafana with
  the `frser-sqlite-datasource` plugin, DB mounted read-only), provisioned
  datasources, and a two-section dashboard (`tradovate-success.json`) — LIVE
  panels from Prometheus, OF-RECORD panels from SQLite, every panel
  source-labeled, database wins on disagreement. 11 new tests (150 total).
  README §15 rewritten as **Observability & Monitoring**: three layers
  (Prometheus / SQLite / logs), run instructions, and an honest split of
  the metrics table into implemented vs planned (the old table presented
  ten unbuilt design-spec metrics as existing).
- **Live market-data loop** (`main.py`): reconnecting MD websocket stream — gateway auth, `md/subscribeDOM` + `md/subscribeQuote`, events routed through `MdRouter` into the engine; drop-and-resync on disconnect, graceful SIGINT/SIGTERM shutdown. `dry_run: true` now runs against real market data instead of exiting with code 3.
- **`LiveExecutor`** (`src/trading/live_executor.py`): implements the `Executor` protocol against Tradovate REST — OSO bracket entries via `placeoso`, quadrant-trail stop modification, liquidation on flatten, entry-only cancel on blackout (protective stop survives). Wired in automatically when `dry_run: false`.
- **`UserSyncRouter`** (`src/trading/user_sync.py`): routes trading-socket `user/syncrequest` fill/rejection events to `engine.on_fill` / `on_order_nack`. All event shapes it depends on verified on demo (see soak round 3) — unrecognized events are logged and dropped.
- **Demo/live startup safety checks**: refuses to start if `user/syncrequest` is denied (no trading without fill confirmations), if the account already holds a position in the contract, or if the auth response lacks `mdAccessToken`; trading-socket watchdog stops the bot if fill events are lost.
- **One-bracket guard** (`LiveExecutor`): a new entry is refused while a previous entry is still tracked; released when fills round-trip the position to flat (`note_fill`), by flatten, or by cancel. Caps un-acknowledged exposure at one bracket if fill events are never recognized.
- **`scripts/capture_user_sync.py`**: read-only soak tool that records raw `user/syncrequest` frames to `logs/*.jsonl` — the verification step that closes the "user-data event shapes unverified" ⚠ in `docs/API-document.md`.
- 19 offline tests for `LiveExecutor` and `UserSyncRouter` (119 total passing).
- Real-frame fixture tests for `UserSyncRouter` (`TestUserSyncRouterDemoFrames`): verbatim demo frames for buy/sell fills, canceled orders, suspended bracket legs, and executionReport/orderStrategy pass-through.
- **`scripts/check_md_access.py`**: read-only probe that validates market-data entitlement end to end — mdAccessToken presence, MD socket authorization, `md/subscribeQuote`/`md/subscribeDOM` acceptance, and a live-event count.

### Fixed

- **`_md_loop` treated refused MD subscriptions as success** (`main.py`): `md/subscribe*` refusals answer `s: 200` with the error inside `d` (`errorText: "Symbol is inaccessible"`, `mode: "None"`), so the old `s != 200` check would log "MD stream up" and wait forever on a feed that never comes. Both `_md_loop` and the probe now judge acceptance on `d`.

### Verified

- **Demo soak round 3** (2026-08-18) — `user/syncrequest` event shapes captured live via `scripts/capture_user_sync.py` (~850 frames across three captures, manual orders on MESU6 contract 4399631): `fill Created` matches `UserSyncRouter`'s parsing exactly, and partial fills arrive as multiple independent `fill Created` frames; observed `ordStatus` lifecycle `Unknown → PendingNew → Working → Filled` plus `Canceled`/`Suspended`/`Rejected`; UI brackets arrive as `orderStrategy` entities. **Rejections verified live** (`MaxOrderQtyLimitReached`): the order frame carries `ordStatus: "Rejected"` exactly as the nack branch expects, with the reason text on a separate `commandReport` (`RiskRejected`). All user-data shapes the router depends on are now demo-verified.

## [0.1.0] - 2026-08-16

First working prototype: full pipeline from architecture design through demo-environment soak testing (~100 tests passing).

### Added

- **Phase 1** — SQLite storage layer and config loaders with contract validation (`b5ac0e6`)
- **Phase 2** — CME volume/open-interest fetcher and active-contract resolver (`cdf2910`)
- **Phase 3** — ForexFactory economic calendar integration and reference daemon (`5d0a1c6`)
- **Phase 4** — Tradovate auth, single-session gateway, REST client, and WebSocket frame codec (`32d8fc4`)
- **Phase 5** — Session state machine and news blackout guard, frozen-time tested (`0456eb3`)
- **Phase 6** — Trading engine ported from Kraken to futures: quadrant risk model, symmetric shorts, gated pipeline (`6b56913`)
- **Phase 7** — Multi-product launcher, Prometheus monitoring, and market-data router (`4013a76`)

### Changed

- Simplified `Credentials.from_env` with a fixed `appVersion` default (`7d96b64`)
- Untracked `__pycache__` directories (now gitignored) (`643d7a9`)

### Verified

- **Demo soak round 1** — auth, token renewal, and both WebSocket authorizations (`ccf122a`)
- **Demo soak round 2** — account, cash balance, contract lookup, `placeorder`, and `placeoso` OSO bracket orders (`7aa84f6`)

## Pre-implementation (design phase)

### 2026-08-16

- Hardened trade-management architecture: quadrant trail, strategy router, config documentation (`9215357`)

### 2026-08-12

- Added playbook cards as G1 strategy-lifecycle artifact (`ac5194d`)

### 2026-08-11

- Updated architecture for Tradovate API constraints (`cb9db53`)

### 2026-08-09

- Added README_v1: strategy-lifecycle architecture upgrade (`f46ad00`)

### 2026-08-02

- Changed trading session to 08:00–16:00 ET day session (`9b2b3ef`)
- Encoded trading-strategies playbook into `config.yaml` (`c3f6fad`)
- Moved risk configuration to the product level (`beb3427`)

### 2026-08-01

- Initial Tradovate CME futures bot architecture design (`26723fe`)
