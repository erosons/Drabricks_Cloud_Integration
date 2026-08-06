"""
Kraken Account Exporter — polls Kraken private API every 60 s and exposes
account balance and last 20 closed orders as Prometheus metrics on port 9300.

Metrics:
  kraken_balance_usd{asset}           — per-asset balance (all assets)
  kraken_trade_equity_usd             — net equity in USD
  kraken_trade_unrealized_pnl_usd     — open position uPnL in USD
  kraken_closed_order_price{...}      — avg execution price
  kraken_closed_order_vol_exec{...}   — executed volume
  kraken_closed_order_cost_usd{...}   — order cost in USD
  kraken_closed_order_fee_usd{...}    — fee paid in USD
  kraken_closed_order_close_time{...} — close timestamp (unix)
"""

import base64
import hashlib
import hmac
import logging
import os
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread, Lock

import requests
from prometheus_client import Gauge, Info, generate_latest, CONTENT_TYPE_LATEST, REGISTRY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ACCT] %(message)s")
log = logging.getLogger("kraken_account")

PORT          = int(os.getenv("ACCOUNT_EXPORTER_PORT", "9300"))
POLL_INTERVAL = int(os.getenv("ACCOUNT_POLL_INTERVAL", "60"))
API_KEY       = os.getenv("KRAKEN_API_KEY", "")
API_SECRET    = os.getenv("KRAKEN_API_SECRET", "")
BASE_URL      = "https://api.kraken.com"

# ── Prometheus metrics ────────────────────────────────────────────────────────

balance_gauge   = Gauge("kraken_balance_usd",           "Kraken asset balance", ["asset"])
equity_gauge    = Gauge("kraken_trade_equity_usd",       "Kraken net equity in USD")
upnl_gauge      = Gauge("kraken_trade_unrealized_pnl_usd", "Kraken open position uPnL in USD")

order_price     = Gauge("kraken_closed_order_price",      "Avg fill price of closed order",
                        ["txid", "pair", "side"])
order_vol       = Gauge("kraken_closed_order_vol_exec",   "Executed volume of closed order",
                        ["txid", "pair", "side"])
order_cost      = Gauge("kraken_closed_order_cost_usd",   "Cost/proceeds of closed order in USD",
                        ["txid", "pair", "side"])
order_fee       = Gauge("kraken_closed_order_fee_usd",    "Fee paid for closed order in USD",
                        ["txid", "pair", "side"])
order_close_ts  = Gauge("kraken_closed_order_close_time", "Close timestamp (unix epoch)",
                        ["txid", "pair", "side"])

# ── Kraken API helpers ────────────────────────────────────────────────────────

def _nonce() -> str:
    return str(int(time.time_ns() // 1_000))


def _sign(urlpath: str, data: dict) -> str:
    postdata = urllib.parse.urlencode(data)
    encoded  = (str(data["nonce"]) + postdata).encode()
    message  = urlpath.encode() + hashlib.sha256(encoded).digest()
    mac      = hmac.new(base64.b64decode(API_SECRET), message, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()


def _private(endpoint: str, params: dict | None = None) -> dict:
    urlpath = f"/0/private/{endpoint}"
    url     = f"{BASE_URL}{urlpath}"
    data: dict = dict(params or {})
    data["nonce"] = _nonce()
    headers = {
        "API-Key":      API_KEY,
        "API-Sign":     _sign(urlpath, data),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    resp = requests.post(url, headers=headers, data=urllib.parse.urlencode(data), timeout=10)
    resp.raise_for_status()
    body = resp.json()
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body["result"]


# ── Poll loop ─────────────────────────────────────────────────────────────────

# Track which (txid, pair, side) label sets we've seen so we can clear stale ones
_seen_orders: set[tuple] = set()
_lock = Lock()


def _refresh():
    global _seen_orders

    # --- Balance ---
    try:
        bal = _private("Balance")
        for asset, amount in bal.items():
            balance_gauge.labels(asset=asset).set(float(amount))
        log.info("Balance updated: %d assets", len(bal))
    except Exception as exc:
        log.warning("Balance fetch failed: %s", exc)

    # --- Trade balance (equity + uPnL) ---
    try:
        tb = _private("TradeBalance", {"asset": "ZUSD"})
        equity_gauge.set(float(tb.get("e", 0)))
        upnl_gauge.set(float(tb.get("n", 0)))
        log.info("Trade balance: equity=%.2f uPnL=%.2f", float(tb.get("e", 0)), float(tb.get("n", 0)))
    except Exception as exc:
        log.warning("TradeBalance fetch failed: %s", exc)

    # --- Last 20 closed orders ---
    try:
        result = _private("ClosedOrders", {"trades": "false"})
        orders = result.get("closed", {})

        # Sort by close time desc, take 20
        sorted_orders = sorted(
            orders.items(),
            key=lambda kv: float(kv[1].get("closetm", 0)),
            reverse=True,
        )[:20]

        new_seen: set[tuple] = set()
        for txid, o in sorted_orders:
            descr = o.get("descr", {})
            pair  = descr.get("pair", "UNKNOWN")
            side  = descr.get("type", "unknown")   # "buy" or "sell"
            key   = (txid, pair, side)
            new_seen.add(key)

            order_price.labels(txid=txid, pair=pair, side=side).set(float(o.get("price", 0)))
            order_vol.labels(txid=txid, pair=pair, side=side).set(float(o.get("vol_exec", 0)))
            order_cost.labels(txid=txid, pair=pair, side=side).set(float(o.get("cost", 0)))
            order_fee.labels(txid=txid, pair=pair, side=side).set(float(o.get("fee", 0)))
            order_close_ts.labels(txid=txid, pair=pair, side=side).set(float(o.get("closetm", 0)))

        # Remove labels for orders that dropped out of top-20
        with _lock:
            for stale in _seen_orders - new_seen:
                t, p, s = stale
                try:
                    order_price.remove(t, p, s)
                    order_vol.remove(t, p, s)
                    order_cost.remove(t, p, s)
                    order_fee.remove(t, p, s)
                    order_close_ts.remove(t, p, s)
                except Exception:
                    pass
            _seen_orders = new_seen

        log.info("Closed orders updated: %d fetched", len(sorted_orders))
    except Exception as exc:
        log.warning("ClosedOrders fetch failed: %s", exc)


def _poll_loop():
    while True:
        _refresh()
        time.sleep(POLL_INTERVAL)


# ── HTTP server ───────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            output = generate_latest(REGISTRY)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(output)
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    if not API_KEY or not API_SECRET:
        raise SystemExit("KRAKEN_API_KEY and KRAKEN_API_SECRET must be set")

    log.info("Starting Kraken Account Exporter on port %d (poll every %ds)", PORT, POLL_INTERVAL)

    # Prime metrics before first scrape
    _refresh()

    # Background poll thread
    t = Thread(target=_poll_loop, daemon=True)
    t.start()

    server = HTTPServer(("0.0.0.0", PORT), _Handler)
    server.serve_forever()
