"""
Market scanner — runs continuously, polling every 5 minutes.

Eligibility criteria (all four must pass):
  • Market cap       ≥ $300M
  • Volume 24h       ≥ $1M
  • Listed on        Binance, Coinbase, OR Kraken
  • Vol/MC ratio     ≥ 5%  (active trading interest)

Output sections each cycle:
  1. ELIGIBLE KRAKEN PAIRS   — qualified coins on Kraken (add/configured status)
  2. ELIGIBLE (not on Kraken) — qualified coins on Binance/Coinbase only
  3. TOP MOVERS              — 10–50% 24h moves
  4. CONFIGURED PAIRS FAILING — env files whose coins dropped below thresholds

Run:  python market_scanner.py
Stop: Ctrl-C
"""

import json
import logging
import os
import signal
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

# ── Config ────────────────────────────────────────────────────────────────────

POLL_INTERVAL_SEC  = 300
CMC_PAGE_SIZE      = 500
MIN_MARKET_CAP     = 300_000_000
MIN_VOL_24H        = 1_000_000
MIN_VOL_MC_RATIO   = 5.0
MOVE_LOW_PCT       = 10.0
MOVE_HIGH_PCT      = 50.0
OTHER_ELIGIBLE_CAP = 25
EXCHANGE_REFRESH_SEC = 3600  # re-fetch exchange listings every hour

LOG_FILE  = Path("logs/scanner.log")
PAIRS_DIR = Path("pairs")

CMC_URL = (
    "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing"
    "?start=1&limit={limit}&sortBy=market_cap&sortType=desc"
    "&convert=USD&cryptoType=all&tagType=all&audited=false"
    "&aux=cmc_rank,percent_change_1h,percent_change_24h,percent_change_7d,volume_24h"
)

KRAKEN_URL   = "https://api.kraken.com/0/public/AssetPairs"
BINANCE_URL  = "https://api.binance.com/api/v3/exchangeInfo"
COINBASE_URL = "https://api.exchange.coinbase.com/products"

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_FILE.parent.mkdir(exist_ok=True)
log = logging.getLogger("scanner")
log.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s [SCANNER] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
_fh  = logging.FileHandler(LOG_FILE)
_fh.setFormatter(_fmt)
_sh  = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)
log.addHandler(_fh)
log.addHandler(_sh)

# ── Data ──────────────────────────────────────────────────────────────────────

@dataclass
class Coin:
    rank:        int
    symbol:      str
    name:        str
    price:       float
    pct_1h:      float
    pct_24h:     float
    pct_7d:      float
    vol_24h:     float
    market_cap:  float
    vol_mc_pct:  float
    on_kraken:   bool
    on_binance:  bool
    on_coinbase: bool
    env_exists:  bool

    @property
    def on_any(self) -> bool:
        return self.on_kraken or self.on_binance or self.on_coinbase

    @property
    def exchanges(self) -> str:
        parts = []
        if self.on_kraken:   parts.append("K")
        if self.on_binance:  parts.append("B")
        if self.on_coinbase: parts.append("C")
        return "/".join(parts) or "—"

    @property
    def eligible(self) -> bool:
        return (
            self.market_cap  >= MIN_MARKET_CAP  and
            self.vol_24h     >= MIN_VOL_24H      and
            self.on_any                          and
            self.vol_mc_pct  >= MIN_VOL_MC_RATIO
        )

    @property
    def is_mover(self) -> bool:
        return MOVE_LOW_PCT <= abs(self.pct_24h) <= MOVE_HIGH_PCT


# ── Fetchers ──────────────────────────────────────────────────────────────────

def _fetch(url: str, timeout: int = 20) -> Optional[Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        log.warning("Fetch failed [%s]: %s", url[:60], exc)
        return None


def _kraken_symbols() -> Set[str]:
    data = _fetch(KRAKEN_URL)
    if not data:
        return set()
    out = set()
    for v in data.get("result", {}).values():
        ws = v.get("wsname", "")
        if ws.endswith("/USD"):
            out.add(ws[:-4].upper())
    return out


def _binance_symbols() -> Set[str]:
    data = _fetch(BINANCE_URL, timeout=30)
    if not data or not isinstance(data, dict):
        return set()
    out = set()
    for s in data.get("symbols", []):
        if s.get("quoteAsset") in ("USDT", "BUSD", "USD") and s.get("status") == "TRADING":
            out.add(s["baseAsset"].upper())
    return out


def _coinbase_symbols() -> Set[str]:
    data = _fetch(COINBASE_URL)
    if not data or not isinstance(data, list):
        return set()
    out = set()
    for p in data:
        if p.get("quote_currency") in ("USD", "USDC") and p.get("status") == "online":
            out.add(p["base_currency"].upper())
    return out


def _configured_symbols() -> Set[str]:
    return {p.stem.upper() for p in PAIRS_DIR.glob("*.env")}


def _fetch_coins(
    kraken: Set[str],
    binance: Set[str],
    coinbase: Set[str],
    configured: Set[str],
) -> List[Coin]:
    data = _fetch(CMC_URL.format(limit=CMC_PAGE_SIZE))
    if not data:
        return []

    coins = []
    for c in data.get("data", {}).get("cryptoCurrencyList", []):
        quotes = c.get("quotes", [{}])
        q      = quotes[0] if quotes else {}
        price  = float(q.get("price",           0.0) or 0.0)
        vol    = float(q.get("volume24h",        0.0) or 0.0)
        mc     = float(q.get("marketCap",        0.0) or 0.0)
        pct24  = float(q.get("percentChange24h", 0.0) or 0.0)
        pct1h  = float(q.get("percentChange1h",  0.0) or 0.0)
        pct7d  = float(q.get("percentChange7d",  0.0) or 0.0)
        sym    = c.get("symbol", "").upper()
        ratio  = (vol / mc * 100.0) if mc > 0 else 0.0

        coins.append(Coin(
            rank        = int(c.get("cmcRank", 9999)),
            symbol      = sym,
            name        = c.get("name", ""),
            price       = price,
            pct_1h      = pct1h,
            pct_24h     = pct24,
            pct_7d      = pct7d,
            vol_24h     = vol,
            market_cap  = mc,
            vol_mc_pct  = ratio,
            on_kraken   = sym in kraken,
            on_binance  = sym in binance,
            on_coinbase = sym in coinbase,
            env_exists  = sym in configured,
        ))

    return coins


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_usd(v: float) -> str:
    if v >= 1_000_000_000:
        return f"${v/1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    return f"${v/1_000:.0f}K"


def _print_eligible(coins: List[Coin]) -> None:
    eligible        = [c for c in coins if c.eligible]
    kraken_eligible = sorted([c for c in eligible if c.on_kraken],    key=lambda c: c.vol_mc_pct, reverse=True)
    other_eligible  = sorted([c for c in eligible if not c.on_kraken], key=lambda c: c.vol_mc_pct, reverse=True)

    header = "  %-5s  %-10s  %10s  %10s  %12s  %7s  %8s  %7s  %-7s  %s"
    row    = "  %-5d  %-10s  %10.5g  %10s  %12s  %6.1f%%  %+7.1f%%  %+6.1f%%  %-7s  %s"
    cols   = ("Rank", "Symbol", "Price", "Vol24h", "MarketCap", "V/MC%", "24h%", "7d%", "Exch", "Status")

    log.info("─" * 95)
    log.info("ELIGIBLE KRAKEN PAIRS  (MC≥$300M | Vol≥$1M | V/MC≥5%%)  — %d coins", len(kraken_eligible))
    log.info("─" * 95)
    if kraken_eligible:
        log.info(header, *cols)
        log.info("  " + "-" * 92)
        for c in kraken_eligible:
            status = "CONFIGURED" if c.env_exists else "*** ADD ***"
            log.info(row, c.rank, c.symbol, c.price,
                     _fmt_usd(c.vol_24h), _fmt_usd(c.market_cap),
                     c.vol_mc_pct, c.pct_24h, c.pct_7d, c.exchanges, status)
    else:
        log.info("  None found in top %d CMC coins", CMC_PAGE_SIZE)

    if other_eligible:
        log.info("")
        log.info("ELIGIBLE — not on Kraken yet  (%d total, top %d shown)",
                 len(other_eligible), OTHER_ELIGIBLE_CAP)
        log.info("  " + "-" * 92)
        for c in other_eligible[:OTHER_ELIGIBLE_CAP]:
            log.info(row, c.rank, c.symbol, c.price,
                     _fmt_usd(c.vol_24h), _fmt_usd(c.market_cap),
                     c.vol_mc_pct, c.pct_24h, c.pct_7d, c.exchanges, "")


def _print_movers(coins: List[Coin]) -> None:
    movers  = [c for c in coins if c.is_mover]
    gainers = sorted([c for c in movers if c.pct_24h > 0], key=lambda c: c.pct_24h, reverse=True)
    losers  = sorted([c for c in movers if c.pct_24h < 0], key=lambda c: c.pct_24h)

    header = "  %-5s  %-10s  %10s  %8s  %7s  %7s  %10s  %-7s  %s"
    row    = "  %-5d  %-10s  %10.5g  %+7.1f%%  %+6.1f%%  %+6.1f%%  %10s  %-7s  %s"
    cols   = ("Rank", "Symbol", "Price", "24h%", "1h%", "7d%", "Vol24h", "Exch", "Status")

    for group, label, arrow in [(gainers, "GAINERS", "▲"), (losers, "LOSERS", "▼")]:
        log.info("")
        log.info("─" * 95)
        log.info("%s  TOP MOVERS / %s  (10–50%% 24h)  —  %d coins", arrow, label, len(group))
        log.info("─" * 95)
        if not group:
            log.info("  None in range")
            continue
        log.info(header, *cols)
        log.info("  " + "-" * 92)
        for c in group:
            if c.eligible:
                status = "ELIGIBLE+CFG" if c.env_exists else "ELIGIBLE"
            elif c.on_kraken:
                status = "KRAKEN+CFG"  if c.env_exists else "KRAKEN"
            else:
                status = c.exchanges
            log.info(row, c.rank, c.symbol, c.price,
                     c.pct_24h, c.pct_1h, c.pct_7d,
                     _fmt_usd(c.vol_24h), c.exchanges, status)


def _print_failing(coins: List[Coin]) -> None:
    failing = [c for c in coins if c.env_exists and not c.eligible]
    if not failing:
        return
    log.info("")
    log.info("─" * 95)
    log.info("CONFIGURED PAIRS FAILING ELIGIBILITY  — %d  (consider removing)", len(failing))
    log.info("─" * 95)
    for c in failing:
        reasons = []
        if c.market_cap < MIN_MARKET_CAP:
            reasons.append(f"MC={_fmt_usd(c.market_cap)}<$300M")
        if c.vol_24h < MIN_VOL_24H:
            reasons.append(f"Vol={_fmt_usd(c.vol_24h)}<$1M")
        if not c.on_any:
            reasons.append("not on any exchange")
        if c.vol_mc_pct < MIN_VOL_MC_RATIO:
            reasons.append(f"V/MC={c.vol_mc_pct:.1f}%<5%")
        log.info("  %-10s  CMC#%-4d  MC=%-8s  Vol=%-8s  V/MC=%5.1f%%  | %s",
                 c.symbol, c.rank, _fmt_usd(c.market_cap), _fmt_usd(c.vol_24h),
                 c.vol_mc_pct, " · ".join(reasons))


def _run_once(
    kraken: Set[str],
    binance: Set[str],
    coinbase: Set[str],
) -> None:
    configured = _configured_symbols()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log.info("")
    log.info("━" * 95)
    log.info("  SCAN  %s  |  Configured pairs: %d", ts, len(configured))
    log.info("━" * 95)

    coins = _fetch_coins(kraken, binance, coinbase, configured)
    if not coins:
        log.warning("No CMC data — skipping cycle")
        return

    _print_eligible(coins)
    _print_movers(coins)
    _print_failing(coins)
    log.info("")
    log.info("Next scan in %ds", POLL_INTERVAL_SEC)


# ── Main loop ─────────────────────────────────────────────────────────────────

_running = True


def _handle_signal(signum, frame):
    global _running
    log.info("Shutdown signal — stopping scanner.")
    _running = False


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT,  _handle_signal)


def main() -> None:
    log.info("=" * 95)
    log.info("Market Scanner started  |  MC≥$300M  Vol≥$1M  V/MC≥5%%  |  poll=%ds  |  top=%d CMC",
             POLL_INTERVAL_SEC, CMC_PAGE_SIZE)
    log.info("=" * 95)

    kraken:   Set[str] = set()
    binance:  Set[str] = set()
    coinbase: Set[str] = set()
    last_exchange_refresh = 0.0

    while _running:
        now = time.time()
        if now - last_exchange_refresh > EXCHANGE_REFRESH_SEC:
            log.info("Refreshing exchange listings ...")
            kraken   = _kraken_symbols()
            binance  = _binance_symbols()
            coinbase = _coinbase_symbols()
            last_exchange_refresh = now
            log.info("Kraken=%d  Binance=%d  Coinbase=%d", len(kraken), len(binance), len(coinbase))

        _run_once(kraken, binance, coinbase)

        for _ in range(POLL_INTERVAL_SEC):
            if not _running:
                break
            time.sleep(1)

    log.info("Scanner stopped.")


if __name__ == "__main__":
    main()
