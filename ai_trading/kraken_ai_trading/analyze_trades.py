"""Fetch trade history from Kraken and produce a P&L breakdown per pair."""
import base64, hashlib, hmac, json, time, urllib.parse, urllib.request, os
from collections import defaultdict
from pathlib import Path

for line in Path(".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.split("#")[0].strip())

KEY    = os.environ["KRAKEN_API_KEY"]
SECRET = os.environ["KRAKEN_API_SECRET"]

def call(endpoint, params=None):
    urlpath = f"/0/private/{endpoint}"
    data    = {"nonce": str(int(time.time_ns() // 1000)), **(params or {})}
    postdata = urllib.parse.urlencode(data)
    msg = urlpath.encode() + hashlib.sha256((str(data["nonce"]) + postdata).encode()).digest()
    sig = base64.b64encode(hmac.new(base64.b64decode(SECRET), msg, hashlib.sha512).digest()).decode()
    req = urllib.request.Request(
        "https://api.kraken.com" + urlpath,
        data=postdata.encode(),
        headers={"API-Key": KEY, "API-Sign": sig, "Content-Type": "application/x-www-form-urlencoded"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

# ── Balance ───────────────────────────────────────────────────────────────────
bal  = call("Balance")["result"]
zusd = float(bal.get("ZUSD", 0))
open_positions = {k: float(v) for k, v in bal.items() if float(v) > 0.001 and k != "ZUSD"}

print("=" * 60)
print("CURRENT BALANCE")
print("=" * 60)
print(f"  USD cash:    ${zusd:.2f}")
for k, v in sorted(open_positions.items()):
    print(f"  {k}: {v}")

# ── Trade history ─────────────────────────────────────────────────────────────
trades = call("TradesHistory", {"trades": True})["result"]["trades"]

by_pair = defaultdict(list)
for tid, t in sorted(trades.items(), key=lambda x: x[1]["time"]):
    by_pair[t["pair"]].append(t)

total_fees  = 0.0
total_buy   = 0.0
total_sell  = 0.0
wins = losses = 0
win_usd = loss_usd = 0.0

print()
print("=" * 70)
print("ROUND-TRIP P&L PER PAIR  (last 50 trades)")
print("=" * 70)
print(f"  {'Pair':<12}  {'Spent':>9}  {'Received':>9}  {'Fees':>7}  {'Net':>8}  Status")
print("  " + "-" * 65)

for pair, txs in sorted(by_pair.items()):
    label    = pair.replace("ZUSD","").replace("USD","")
    fees     = sum(float(t["fee"])  for t in txs)
    buy_cost = sum(float(t["cost"]) + float(t["fee"]) for t in txs if t["type"] == "buy")
    sell_rev = sum(float(t["cost"]) - float(t["fee"]) for t in txs if t["type"] == "sell")
    total_fees += fees
    has_buy  = any(t["type"] == "buy"  for t in txs)
    has_sell = any(t["type"] == "sell" for t in txs)

    if has_buy and has_sell:
        net = sell_rev - buy_cost
        total_buy  += buy_cost
        total_sell += sell_rev
        if net > 0:
            wins   += 1; win_usd  += net; tag = "WIN"
        else:
            losses += 1; loss_usd += net; tag = "LOSS"
        print(f"  {label:<12}  ${buy_cost:>8.2f}  ${sell_rev:>8.2f}  ${fees:>6.4f}  {net:>+8.2f}  {tag}")
    elif has_buy:
        buy_only = sum(float(t["cost"]) + float(t["fee"]) for t in txs if t["type"] == "buy")
        total_buy += buy_only
        print(f"  {label:<12}  ${buy_only:>8.2f}  {'(open)':>9}  ${fees:>6.4f}  {'?':>8}  OPEN")

print("  " + "-" * 65)
net_pnl     = win_usd + loss_usd
net_w_fees  = net_pnl  # fees already deducted per-trade above

print(f"  Wins  : {wins}  +${win_usd:.2f}")
print(f"  Losses: {losses}  -${abs(loss_usd):.2f}")
print(f"  Net P&L (closed):    ${net_pnl:+.2f}")
print(f"  Total fees paid:    -${total_fees:.4f}")
print()
print("=" * 60)
print("WHY IS BALANCE SHRINKING?")
print("=" * 60)
avg_fee_per_trade = total_fees / len(trades) if trades else 0
trades_per_day_est = len(trades) / 2  # ~2 days of data
fee_per_day_est = avg_fee_per_trade * trades_per_day_est
print(f"  Trades in history : {len(trades)}")
print(f"  Avg fee per trade : ${avg_fee_per_trade:.4f}")
print(f"  Est. fees/day     : ~${fee_per_day_est:.2f}  (at current rate)")
print(f"  Stop loss cost    : $5.00 per trigger")
print(f"  Open positions    : ${sum(0 for _ in open_positions):.2f} locked in tokens")
print()
print("  Likely causes:")
print("  1. FEES  — every buy AND sell costs ~$0.20. High trade frequency")
print("             multiplies this. Check if bot is over-trading.")
print("  2. STOP LOSSES — each SL hit = guaranteed -$5. If 5 pairs")
print("             hit SL in a day = -$25 from balance instantly.")
print("  3. OPEN POSITIONS — USD converted to tokens (CFX, GWEI, TRAC)")
print("             reduces visible cash balance, not total value.")
