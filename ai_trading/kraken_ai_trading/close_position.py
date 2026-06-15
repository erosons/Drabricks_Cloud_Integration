#!/usr/bin/env python3
"""Close a Kraken position at a target price.

Usage:
    python close_position.py SAND 0.0521             # sell full SAND balance
    python close_position.py XRP 2.10                # sell full XRP balance
    python close_position.py SAND 0.0521 --qty 500   # sell specific qty
    python close_position.py ETH 3600 --side buy     # buy (close short)
    python close_position.py SAND 0.0521 --dry-run   # preview only
    python close_position.py SAND 0.0521 --yes       # skip confirmation prompt
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.split("#")[0].strip()
        os.environ.setdefault(key.strip(), val)


_load_env(Path(__file__).parent / ".env")

API_KEY    = os.getenv("KRAKEN_API_KEY", "")
API_SECRET = os.getenv("KRAKEN_API_SECRET", "")
BASE_URL   = "https://api.kraken.com"

# Kraken balance keys differ for legacy asset names
_BALANCE_MAP = {
    "BTC":  "XXBT",
    "ETH":  "XETH",
    "XRP":  "XXRP",
    "XLM":  "XXLM",
    "DOGE": "XXDOGE",
    "ZEC":  "XZEC",
    "LTC":  "XLTC",
    "ETC":  "XETC",
}


def _nonce() -> str:
    return str(int(time.time_ns() // 1_000))


def _sign(urlpath: str, data: dict) -> str:
    postdata = urllib.parse.urlencode(data)
    encoded  = (str(data["nonce"]) + postdata).encode()
    msg      = urlpath.encode() + hashlib.sha256(encoded).digest()
    mac      = hmac.new(base64.b64decode(API_SECRET), msg, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()


def _call(endpoint: str, params=None) -> dict:
    if not API_KEY or not API_SECRET:
        sys.exit("ERROR: KRAKEN_API_KEY / KRAKEN_API_SECRET not set in .env")
    urlpath = f"/0/private/{endpoint}"
    data    = {"nonce": _nonce(), **(params or {})}
    headers = {
        "API-Key":      API_KEY,
        "API-Sign":     _sign(urlpath, data),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    req  = urllib.request.Request(
        BASE_URL + urlpath,
        data=urllib.parse.urlencode(data).encode(),
        headers=headers,
    )
    resp   = urllib.request.urlopen(req, timeout=15)
    result = json.loads(resp.read())
    if result.get("error"):
        sys.exit(f"Kraken error: {result['error']}")
    return result["result"]


def get_balance(token: str) -> float:
    balances = _call("Balance")
    key = _BALANCE_MAP.get(token.upper(), token.upper())
    val = float(balances.get(key, 0.0))
    if val == 0.0:
        # show all non-zero balances to help diagnose wrong symbol
        nonzero = {k: v for k, v in balances.items() if float(v) > 0}
        print(f"  Available balances: {nonzero}", file=sys.stderr)
    return val


def fmt_vol(qty: float) -> str:
    return f"{qty:.8f}".rstrip("0").rstrip(".")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Place a limit order to close a position at a target price.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("token",        help="Token symbol  e.g. SAND XRP ETH BTC")
    ap.add_argument("price", type=float, help="Limit price in USD")
    ap.add_argument("--qty",  type=float, default=None,
                    help="Volume (default: full balance when selling)")
    ap.add_argument("--side", choices=["sell", "buy"], default="sell",
                    help="Order side (default: sell)")
    ap.add_argument("--pair", default=None,
                    help="Override pair name, e.g. XXBTZUSD (use when TOKEN/USD is rejected)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show order details without placing it")
    ap.add_argument("--yes",  action="store_true",
                    help="Skip confirmation prompt")
    args = ap.parse_args()

    token = args.token.upper()
    pair  = args.pair if args.pair else f"{token}/USD"

    if args.qty is not None:
        qty = args.qty
    else:
        print(f"Fetching {token} balance ...", flush=True)
        qty = get_balance(token)
        if qty <= 0:
            sys.exit(f"No {token} balance found (got {qty}). "
                     "Use --qty to specify volume manually.")

    vol_str   = fmt_vol(qty)
    usd_value = qty * args.price

    print()
    print(f"  Pair    : {pair}")
    print(f"  Side    : {args.side.upper()}")
    print(f"  Volume  : {vol_str} {token}")
    print(f"  Price   : {args.price}")
    print(f"  Value   : ~${usd_value:,.2f}")
    print(f"  Mode    : {'DRY RUN — not placing' if args.dry_run else 'LIVE'}")
    print()

    if args.dry_run:
        return

    if not args.yes:
        try:
            confirm = input("Place order? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return
        if confirm != "y":
            print("Cancelled.")
            return

    result = _call("AddOrder", {
        "pair":      pair,
        "type":      args.side,
        "ordertype": "limit",
        "price":     str(args.price),
        "volume":    vol_str,
    })

    txids = result.get("txid", [])
    desc  = result.get("descr", {}).get("order", "")
    print(f"  Order placed!")
    print(f"  ID   : {txids[0] if txids else 'unknown'}")
    print(f"  Desc : {desc}")
    print()


if __name__ == "__main__":
    main()
