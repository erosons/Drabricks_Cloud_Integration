# Tradovate API — Endpoint & Protocol Reference

The subset of the Tradovate API this bot uses, with exact shapes. Sources:
the official tutorial repo ([tradovate/example-api-js](https://github.com/tradovate/example-api-js),
verified 2026-08-16) and the API reference at <https://api.tradovate.com>.
Items marked **⚠ verify at demo soak** are shapes to confirm against the demo
environment during roadmap Phase 8 before anything touches live.

Constraint-level rules (rate caps, single-session, `isAutomated`, penalty
tickets, auto-liquidation) live in `README.md` §17; this file is the
wire-level companion.

## Environments

| | REST | WebSocket |
|---|---|---|
| Demo | `https://demo.tradovateapi.com/v1` | `wss://demo.tradovateapi.com/v1/websocket` |
| Live | `https://live.tradovateapi.com/v1` | `wss://live.tradovateapi.com/v1/websocket` |
| Market data (both) | — | `wss://md.tradovateapi.com/v1/websocket` |

Selected automatically from the `mode` switches (§2): demo unless
`dry_run: false` **and** `live_trading: true`.

## Authentication

`POST /auth/accesstokenrequest` — body:

```json
{
  "name":       "<TRADOVATE_USERNAME>",
  "password":   "<TRADOVATE_PASSWORD>",
  "appId":      "<TRADOVATE_APP_ID>",
  "appVersion": "1.0",
  "cid":        "<TRADOVATE_CID, integer>",
  "sec":        "<TRADOVATE_SECRET>",
  "deviceId":   "<TRADOVATE_DEVICE_ID, stable per deployment>"
}
```

Success → `{ "accessToken": "...", "expirationTime": "ISO-8601", ... }`
(also `mdAccessToken` for the MD socket, plus account flags: `userStatus`,
`hasMarketData`, `hasLive`, `hasFunded`). Tokens live ~120 minutes; the bot
renews at 60 via `GET /auth/renewaccesstoken` (Authorization header), which
returns the full token payload again — **✓ verified on demo 2026-08-16**.

Account-shape notes verified on demo:
* Google-SSO accounts authenticate with `name: "Google:<numeric id>"` —
  not the email address.
* `appId`/`appVersion` must match the values registered with the API key.
* **API-key permission scopes gate everything past auth**: with no scopes
  granted, `account/list` and `user/syncrequest` return 401
  `Access is denied` (REST and WS alike) and `md/subscribeQuote` returns
  `Symbol is inaccessible` / `UnknownSymbol` even though auth, renewal,
  and both websocket authorizations succeed. Scopes are granted in the
  Tradovate dashboard when editing the API key (Account: Read,
  Orders: Full, Positions: Read, Contract Library: Read,
  Market Data: Read as the bot's minimum set).

### Time-penalty responses

Any endpoint may answer with a penalty instead of data:

```json
{ "p-ticket": "<code>", "p-time": 42, "p-captcha": false }
```

* wait `p-time` **seconds**, then retry the SAME request with `"p-ticket"`
  added to the body;
* `p-captcha: true` cannot be resolved by a bot — log, alert, and back off
  an hour (always the case for over-called `accesstokenrequest`);
* the gateway persists unexpired tickets so a crash-restart cannot
  hot-loop the endpoint (attestation #21–23).

## Accounts & orders (REST, Authorization: `Bearer <accessToken>`)

| Endpoint | Use | Soak |
|---|---|---|
| `GET /account/list` | account id + spec discovery at startup | ✓ 2026-08-16 |
| `POST /cashBalance/getcashbalancesnapshot` `{accountId}` | equity for sizing + margin monitor; keys incl. `netLiq`, `totalCashValue`, `initialMargin`, `maintenanceMargin`, `autoLiqLevel`, `openPnL`, `realizedPnL`, `weekRealizedPnL` | ✓ |
| `GET /contract/find?name=MESU6` / `GET /contract/suggest?t=MES&l=5` | symbol → `contractId` (needed for MD filtering + liquidate) | ✓ |
| `POST /order/placeorder` | plain entry/exit → `{"orderId"}` | ✓ |
| `POST /order/placeoso` | entry + server-side stop → `{"orderId","oso1Id"}` | ✓ |
| `GET /order/item?id=` | order state (`ordStatus`: Working/Rejected/…) | ✓ |
| `POST /order/modifyorder` | trailing engine moving the resting stop | ⚠ needs open market |
| `POST /order/cancelorder` | working-order cancel; answers `{"failureReason":"TooLate"}` when the order is already terminal | ✓ |
| `GET /position/list` | flat-check / reconciliation | ✓ |
| `POST /order/liquidateposition` | flatten one product (15:55 ET, disconnect) | ⚠ needs open market |

`placeorder` body (required fields marked):

```json
{
  "accountSpec": "myAccountSpec",
  "accountId":   12345,
  "action":      "Buy",            // required: Buy | Sell
  "symbol":      "MESU6",          // required: ACTIVE month, never the root
  "orderQty":    1,                // required
  "orderType":   "Limit",          // required: Market|Limit|Stop|StopLimit|
                                   //   MIT|TrailingStop|TrailingStopLimit
  "price":       6420.25,          // Limit/StopLimit
  "stopPrice":   6400.00,          // Stop/StopLimit
  "timeInForce": "Day",
  "isAutomated": true              // MANDATORY for this bot, every order (§17)
}
```

`placeoso` = a `placeorder` body plus `bracket1` (and optional `bracket2`),
each a child spec like `{ "action": "Sell", "orderType": "Stop",
"stopPrice": ... }` — **✓ verified on demo**: accepted and returned
`{"orderId": ..., "oso1Id": ...}`.

## WebSocket protocol (trading and MD sockets share it)

Frames are a single indicator char + optional JSON payload:

| Frame | Meaning |
|---|---|
| `o` | socket open — client must now authorize |
| `h` | server heartbeat |
| `a[...]` | array of data/response messages (may batch several) |
| `c` | close |

* **Requests** are text: `url\nid\nquery\nbody` — `id` is a client counter;
  responses echo it as `{"i": id, "s": status, "d": data}`.
* **Authorize**: send request with url `authorize`, body = the access token
  (MD socket: `mdAccessToken`) — **✓ both sockets verified on demo
  2026-08-16 with this codebase's frame codec**.
* **Client heartbeat**: the literal string `[]` roughly every 2.5 s —
  without it the server drops the connection.
* **Market data**: on the MD socket, `md/subscribeQuote`,
  `md/subscribeDOM`, `md/subscribeHistogram`, `md/getChart` with body
  `{"symbol": "MESU6"}`; unsubscribe via the matching `md/unsubscribe*`.
  Under load, frames may batch several symbols and drop stale
  intermediate updates — the DOM book must treat gaps as
  drop-and-resync, never assume continuity (§17, attestation #24–25).
* **User data**: `user/syncrequest` on the trading socket streams order,
  fill, and position events **⚠ still 401 after first scope grant — needs
  its own permission category on the API key; event shapes unverified**.
* **Market data entitlement**: with a valid symbol (`contract/find`
  resolves it) `md/subscribe*` answering `Symbol is inaccessible` means the
  API key's Market Data scope or the account's market-data/API add-on
  subscription is missing — not a symbol-format problem.

## Design mapping

| Concern | Module |
|---|---|
| token + renewal | `src/auth/tradovate_auth.py` |
| single session, rate budget, penalty tickets | `src/client/gateway.py` |
| REST calls | `src/client/rest.py` |
| frame codec + reconnecting socket | `src/client/websocket.py` |
