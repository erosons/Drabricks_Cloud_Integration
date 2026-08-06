"""
NGX Stock Screener — scores and ranks Nigerian equities for investment.

Scoring dimensions (total 100 pts):
  Momentum       25 pts  — price change % today
  Volume         15 pts  — volume vs average
  Dividend       20 pts  — dividend yield, payer status
  Valuation      20 pts  — P/E band, price vs reference
  News sentiment 10 pts  — news mentions of the stock
  Sector         10 pts  — sector momentum from peer price changes

Recommendation bands:
  STRONG BUY  ≥ 75
  BUY         ≥ 55
  WATCH       ≥ 35
  HOLD        ≥ 20
  AVOID        < 20
"""
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from config import WAT
from data.ngx_universe import NGX_UNIVERSE, NGX_BY_SYMBOL, SECTOR_GROUPS
from storage import database as db

log = logging.getLogger(__name__)

RECOMMENDATION_BANDS = [
    (75, "STRONG BUY"),
    (55, "BUY"),
    (35, "WATCH"),
    (20, "HOLD"),
    (0,  "AVOID"),
]

RECOMMENDATION_COLORS = {
    "STRONG BUY": "#00d084",
    "BUY":        "#68d391",
    "WATCH":      "#f6e05e",
    "HOLD":       "#a0aec0",
    "AVOID":      "#f05252",
}


def _recommendation(score: float) -> str:
    for threshold, label in RECOMMENDATION_BANDS:
        if score >= threshold:
            return label
    return "AVOID"


def _risk_level(stock_meta: dict, score: float) -> str:
    cap = stock_meta.get("cap_tier", "SMALL")
    if cap == "LARGE" and score >= 55:
        return "LOW"
    if cap == "LARGE":
        return "MEDIUM"
    if cap == "MID":
        return "MEDIUM" if score >= 45 else "HIGH"
    return "HIGH"


def run() -> List[dict]:
    """
    Score all stocks in the universe and return ranked list.
    Uses live NGX equity data where available; falls back to fundamental-only scoring.
    """
    now = datetime.now(WAT)
    live_equities = {e["symbol"]: e for e in db.latest_equities(999)}
    mpr = db.latest_mpr()
    treasury_rates = db.latest_treasury_rates()
    max_treasury_rate = max((r["rate"] for r in treasury_rates if r.get("rate")), default=20.0)

    # Sector momentum from live data
    sector_momentum = _calc_sector_momentum(live_equities)

    # News sentiment per stock
    stock_sentiment = _calc_stock_sentiment()

    picks = []
    for meta in NGX_UNIVERSE:
        symbol = meta["symbol"]
        live  = live_equities.get(symbol)

        score, rationale = _score_stock(
            meta, live, sector_momentum, stock_sentiment.get(symbol, 0.0),
            mpr, max_treasury_rate,
        )

        rec = _recommendation(score)
        risk = _risk_level(meta, score)

        picks.append({
            "screened_at":    now.isoformat(),
            "symbol":         symbol,
            "name":           meta["name"],
            "sector":         meta["sector"],
            "cap_tier":       meta["cap_tier"],
            "price":          live["price"] if live else None,
            "change_pct":     live["change_pct"] if live else None,
            "volume":         live["volume"] if live else None,
            "dividend":       meta["dividend"],
            "div_yield_est":  meta["div_yield_est"],
            "price_ref":      meta["price_ref"],
            "pe_band":        meta["pe_band"],
            "tags":           ",".join(meta["tags"]),
            "thesis":         meta["thesis"],
            "score":          round(score, 1),
            "recommendation": rec,
            "risk_level":     risk,
            "rationale":      " | ".join(rationale),
            "has_live_price": live is not None,
        })

    picks.sort(key=lambda x: x["score"], reverse=True)
    log.info("Stock screener: scored %d stocks, top pick: %s (%s)",
             len(picks), picks[0]["symbol"] if picks else "-",
             picks[0]["recommendation"] if picks else "-")
    return picks


def _score_stock(
    meta: dict,
    live: Optional[dict],
    sector_momentum: Dict[str, float],
    sentiment: float,
    mpr: float,
    max_treasury: float,
) -> tuple:
    score = 0.0
    rationale = []

    # ── 1. Momentum (25 pts) ─────────────────────────────────────────────────
    if live and live.get("change_pct") is not None:
        chg = live["change_pct"]
        if chg >= 7:
            pts = 25; msg = f"Strong surge +{chg:.1f}%"
        elif chg >= 4:
            pts = 20; msg = f"Positive momentum +{chg:.1f}%"
        elif chg >= 1:
            pts = 14; msg = f"Mild gain +{chg:.1f}%"
        elif chg >= -1:
            pts = 10; msg = "Broadly flat"
        elif chg >= -4:
            pts = 5;  msg = f"Minor pullback {chg:.1f}%"
        else:
            pts = 0;  msg = f"Sharp decline {chg:.1f}%"
        score += pts
        rationale.append(msg)
    else:
        # No live data — neutral baseline on momentum
        score += 10
        rationale.append("Price data pending (market hours)")

    # ── 2. Volume signal (15 pts) ────────────────────────────────────────────
    if live and live.get("volume") and live.get("change_pct") is not None:
        vol = live["volume"]
        # Without average volume, use a heuristic threshold per cap tier
        tier_vol_floors = {"LARGE": 1_000_000, "MID": 300_000, "SMALL": 50_000}
        floor = tier_vol_floors.get(meta["cap_tier"], 200_000)
        if vol >= floor * 3:
            score += 15; rationale.append("Exceptional volume (3× normal)")
        elif vol >= floor * 1.5:
            score += 10; rationale.append("Above-average volume")
        elif vol >= floor:
            score += 6
        else:
            score += 2; rationale.append("Low volume — weak conviction")
    else:
        score += 7  # neutral when no data

    # ── 3. Dividend score (20 pts) ───────────────────────────────────────────
    div_yield = meta.get("div_yield_est", 0)
    if meta["dividend"] and div_yield > 0:
        # Compare to T-Bill max rate as benchmark
        if div_yield >= max_treasury - 2:
            score += 20; rationale.append(f"Dividend yield {div_yield:.1f}% ≈ T-Bill rate")
        elif div_yield >= 7:
            score += 16; rationale.append(f"High dividend yield {div_yield:.1f}%")
        elif div_yield >= 4:
            score += 11; rationale.append(f"Dividend yield {div_yield:.1f}%")
        else:
            score += 6;  rationale.append(f"Low dividend yield {div_yield:.1f}%")
    else:
        score += 3  # no dividend — partial credit for growth potential

    # ── 4. Valuation / P/E band (20 pts) ────────────────────────────────────
    pe = meta.get("pe_band", "MID")
    cap = meta.get("cap_tier", "SMALL")
    if pe == "LOW" and cap in ("LARGE", "MID"):
        score += 20; rationale.append(f"Attractive valuation (low P/E, {cap.lower()} cap)")
    elif pe == "LOW":
        score += 15; rationale.append("Low P/E — value opportunity")
    elif pe == "MID":
        score += 12; rationale.append("Fair valuation (mid P/E)")
    else:
        score += 5;  rationale.append("Premium valuation (high P/E) — priced for perfection")

    # ── 5. News sentiment (10 pts) ───────────────────────────────────────────
    if sentiment > 0.05:
        score += 10; rationale.append("Positive recent news coverage")
    elif sentiment > 0:
        score += 6
    elif sentiment < -0.05:
        score -= 5; rationale.append("Negative news coverage")

    # ── 6. Sector momentum (10 pts) ─────────────────────────────────────────
    sec = meta.get("sector", "")
    sec_mom = sector_momentum.get(sec, 0.0)
    if sec_mom >= 2.0:
        score += 10; rationale.append(f"Sector '{sec}' on a run (+{sec_mom:.1f}% avg)")
    elif sec_mom >= 0.5:
        score += 7
    elif sec_mom < -2.0:
        score -= 5; rationale.append(f"Weak sector environment ({sec_mom:.1f}%)")

    # ── Special adjustments ──────────────────────────────────────────────────
    if "blue-chip" in meta.get("tags", []):
        score += 5; rationale.append("Blue-chip quality")
    if "dollar-revenue" in meta.get("tags", []) or "export" in meta.get("tags", []):
        score += 5; rationale.append("Natural FX hedge (dollar revenue)")
    if "speculative" in meta.get("tags", []) or "penny-stock" in meta.get("tags", []):
        score -= 10; rationale.append("High speculative risk")
    if cap == "LARGE":
        score += 3  # stability premium

    return max(0.0, min(score, 100.0)), rationale


def _calc_sector_momentum(live_equities: dict) -> Dict[str, float]:
    """Average change_pct per sector from live data."""
    sector_changes: Dict[str, List[float]] = {}
    for symbol, eq in live_equities.items():
        meta = NGX_BY_SYMBOL.get(symbol)
        sec = meta["sector"] if meta else eq.get("sector", "")
        chg = eq.get("change_pct")
        if sec and chg is not None:
            sector_changes.setdefault(sec, []).append(chg)
    return {
        sec: sum(vals) / len(vals)
        for sec, vals in sector_changes.items()
        if vals
    }


def _calc_stock_sentiment(hours: int = 24) -> Dict[str, float]:
    """
    Map news sentiment to stock symbols.
    Looks for symbol/company name mentions in recent news titles.
    """
    news = db.query(
        "SELECT title, summary, sentiment FROM news_articles "
        "WHERE published_at >= datetime('now', ?) ORDER BY published_at DESC",
        (f"-{hours} hours",),
    )
    sentiment_map: Dict[str, List[float]] = {}
    for row in news:
        text = ((row["title"] or "") + " " + (row["summary"] or "")).lower()
        sent = row["sentiment"] or 0.0
        for meta in NGX_UNIVERSE:
            symbol = meta["symbol"].lower()
            name_words = meta["name"].lower().split()[:2]  # first two words of name
            if symbol in text or all(w in text for w in name_words if len(w) > 3):
                sentiment_map.setdefault(meta["symbol"], []).append(sent)
    return {
        sym: sum(vals) / len(vals)
        for sym, vals in sentiment_map.items()
        if vals
    }
