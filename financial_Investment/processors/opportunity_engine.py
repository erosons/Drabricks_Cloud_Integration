import logging
from datetime import datetime, timedelta
from typing import List

from config import WAT, OPPORTUNITY_WEIGHTS, ALERT_THRESHOLDS, POLICY_KEYWORDS
from storage import database as db
from storage.models import Opportunity

log = logging.getLogger(__name__)


def _alert_level(score: float) -> str:
    if score >= ALERT_THRESHOLDS["CRITICAL"]:
        return "CRITICAL"
    if score >= ALERT_THRESHOLDS["HIGH"]:
        return "HIGH"
    if score >= ALERT_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


def _expire_stale(now: datetime) -> None:
    """Mark opportunities older than 24h as EXPIRED."""
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE opportunities SET status='EXPIRED' "
            "WHERE status='ACTIVE' AND detected_at < datetime('now','-24 hours')"
        )


def _already_detected(category: str, title: str, hours: int = 6) -> bool:
    rows = db.query(
        "SELECT 1 FROM opportunities WHERE category=? AND title=? "
        "AND detected_at >= datetime('now',?) AND status='ACTIVE'",
        (category, title, f"-{hours} hours"),
    )
    return len(rows) > 0


def run() -> List[Opportunity]:
    now = datetime.now(WAT)
    _expire_stale(now)
    new_opps: List[Opportunity] = []

    new_opps.extend(_check_treasury_vs_mpr(now))
    new_opps.extend(_check_policy_shift(now))
    new_opps.extend(_check_stock_breakouts(now))
    new_opps.extend(_check_open_ipos(now))
    new_opps.extend(_check_fund_rate_changes(now))
    new_opps.extend(_check_news_govt_signals(now))
    new_opps.extend(_check_fx_opportunity(now))

    for opp in new_opps:
        if not _already_detected(opp.category, opp.title):
            try:
                db.insert_opportunity(opp)
            except Exception as e:
                log.debug("Opp insert skip: %s", e)

    log.info("Opportunity engine: %d new signals", len(new_opps))
    return new_opps


# ── Individual Checks ─────────────────────────────────────────────────────────

def _check_treasury_vs_mpr(now: datetime) -> List[Opportunity]:
    opps = []
    mpr = db.latest_mpr()
    rates = db.latest_treasury_rates()
    threshold = mpr - 2.0

    for r in rates:
        rate = r.get("rate", 0)
        instrument = r.get("instrument", "")
        if rate and rate >= threshold:
            score = OPPORTUNITY_WEIGHTS["HIGH_YIELD_TREASURY"]
            # Boost score if rate > MPR
            if rate >= mpr:
                score += 20
            opps.append(Opportunity(
                detected_at=now,
                category="HIGH_YIELD_TREASURY",
                title=f"{instrument} @ {rate:.1f}% (MPR: {mpr}%)",
                description=(
                    f"{instrument} is offering {rate:.1f}% — "
                    f"{'above' if rate >= mpr else 'close to'} the CBN MPR of {mpr}%. "
                    f"Consider locking in treasury returns before rate changes."
                ),
                score=min(score, 100),
                alert_level=_alert_level(min(score, 100)),
                source="DMO",
            ))
    return opps


def _check_policy_shift(now: datetime) -> List[Opportunity]:
    opps = []
    events = db.query(
        "SELECT * FROM policy_events WHERE event_type='MPR' ORDER BY timestamp DESC LIMIT 2"
    )
    if len(events) >= 2:
        current = events[0]["value"]
        previous = events[1]["value"]
        if current and previous and current != previous:
            direction = "RAISED" if current > previous else "LOWERED"
            change = abs(current - previous)
            score = OPPORTUNITY_WEIGHTS["POLICY_SHIFT"] + (change * 5)
            opps.append(Opportunity(
                detected_at=now,
                category="POLICY_SHIFT",
                title=f"CBN {direction} MPR to {current}% (from {previous}%)",
                description=(
                    f"CBN has {direction.lower()} the MPR by {change:.2f}pp to {current}%. "
                    f"{'Higher rates: treasury instruments more attractive.' if direction=='RAISED' else 'Lower rates: equities and real estate may benefit.'}"
                ),
                score=min(score, 100),
                alert_level=_alert_level(min(score, 100)),
                source="CBN",
            ))
    return opps


def _check_stock_breakouts(now: datetime) -> List[Opportunity]:
    opps = []
    equities = db.latest_equities(200)
    for eq in equities:
        chg = eq.get("change_pct", 0) or 0
        symbol = eq.get("symbol", "")
        price = eq.get("price", 0) or 0
        if abs(chg) >= 5.0 and symbol:
            direction = "UP" if chg > 0 else "DOWN"
            score = OPPORTUNITY_WEIGHTS["STOCK_BREAKOUT"] + min(abs(chg) * 2, 30)
            opps.append(Opportunity(
                detected_at=now,
                category="STOCK_BREAKOUT",
                title=f"{symbol} {direction} {abs(chg):.1f}% today @ ₦{price:.2f}",
                description=(
                    f"{eq.get('name', symbol)} moved {chg:+.1f}% to ₦{price:.2f}. "
                    f"{'Strong buying pressure — watch for continuation.' if chg > 0 else 'Significant sell-off — monitor for reversal or further downside.'}"
                ),
                score=min(score, 100),
                alert_level=_alert_level(min(score, 100)),
                source="NGX",
            ))
    # Top 5 biggest movers only
    opps.sort(key=lambda o: o.score, reverse=True)
    return opps[:5]


def _check_open_ipos(now: datetime) -> List[Opportunity]:
    opps = []
    for ipo in db.open_ipos():
        status = ipo.get("status", "")
        company = ipo.get("company", "")
        score = OPPORTUNITY_WEIGHTS["IPO_ALERT"] + (15 if status == "OPEN" else 0)
        price_str = f"@ ₦{ipo['offer_price']:.2f}" if ipo.get("offer_price") else ""
        opps.append(Opportunity(
            detected_at=now,
            category="IPO_ALERT",
            title=f"IPO {status}: {company} {price_str}",
            description=(
                f"{company} has a {status.lower()} IPO{' at ' + price_str if price_str else ''}. "
                f"Sector: {ipo.get('sector', 'N/A')}. "
                f"Closing: {ipo.get('closing_date', 'TBD')}."
            ),
            score=min(score, 100),
            alert_level=_alert_level(min(score, 100)),
            source="SEC-NG",
        ))
    return opps


def _check_fund_rate_changes(now: datetime) -> List[Opportunity]:
    opps = []
    cutoff = now - timedelta(hours=8)
    recent = db.query(
        "SELECT * FROM fund_rates WHERE timestamp >= ? ORDER BY rate DESC",
        (cutoff.isoformat(),),
    )
    # Find providers with very high rates (> 20% NGN or > 8% USD)
    seen = set()
    for r in recent:
        provider = r["provider"]
        product = r["product"]
        rate = r["rate"]
        curr = r["currency"]
        key = f"{provider}:{product}"
        if key in seen or not rate:
            continue
        seen.add(key)

        threshold = 8.0 if curr == "USD" else 20.0
        if rate >= threshold:
            score = OPPORTUNITY_WEIGHTS["FUND_RATE_CHANGE"] + min(rate - threshold, 20)
            opps.append(Opportunity(
                detected_at=now,
                category="FUND_RATE_CHANGE",
                title=f"{provider} {product}: {rate:.1f}% p.a. ({curr})",
                description=(
                    f"{provider} is offering {rate:.1f}% p.a. on {product} in {curr}. "
                    f"This is above market average — consider comparing with treasury alternatives."
                ),
                score=min(score, 100),
                alert_level=_alert_level(min(score, 100)),
                source=provider,
            ))
    opps.sort(key=lambda o: o.score, reverse=True)
    return opps[:6]


def _check_news_govt_signals(now: datetime) -> List[Opportunity]:
    opps = []
    recent_news = db.query(
        "SELECT * FROM news_articles WHERE published_at >= datetime('now','-6 hours') "
        "ORDER BY sentiment DESC LIMIT 50"
    )
    trigger_patterns = [
        (["privatisation", "privatization", "divestment"], "PRIVATISATION", 35),
        (["budget", "supplementary budget", "appropriation"], "BUDGET_MOVE", 30),
        (["eurobond", "sovereign bond", "fgn bond issue"], "BOND_ISSUANCE", 32),
        (["rate hike", "rate cut", "mpc decision", "mpc communique"], "MPC_DECISION", 40),
        (["naira rebound", "naira strengthens", "dollar falls"], "FX_SHIFT", 28),
        (["nnpc listing", "ipo announcement", "public offer opens"], "IPO_SIGNAL", 35),
        (["tax reform", "finance act", "vat", "withholding tax"], "TAX_REFORM", 25),
    ]
    for article in recent_news:
        text = (article["title"] + " " + (article["summary"] or "")).lower()
        for keywords, category, base_score in trigger_patterns:
            if any(kw in text for kw in keywords):
                sentiment_boost = max(0, article["sentiment"] * 10)
                score = base_score + sentiment_boost
                opps.append(Opportunity(
                    detected_at=now,
                    category="GOVT_FISCAL_MOVE",
                    title=f"[{category}] {article['title'][:100]}",
                    description=article.get("summary", "")[:300],
                    score=min(score, 100),
                    alert_level=_alert_level(min(score, 100)),
                    source=article["source"],
                ))
                break
    return opps[:8]


def _check_fx_opportunity(now: datetime) -> List[Opportunity]:
    opps = []
    fx_events = db.query(
        "SELECT * FROM policy_events WHERE event_type='FX_RATE' ORDER BY timestamp DESC LIMIT 2"
    )
    if len(fx_events) >= 2:
        current_rate = fx_events[0]["value"]
        prev_rate = fx_events[1]["value"]
        if current_rate and prev_rate:
            change_pct = (current_rate - prev_rate) / prev_rate * 100
            if abs(change_pct) >= 1.0:
                direction = "depreciated" if change_pct > 0 else "appreciated"
                score = OPPORTUNITY_WEIGHTS["FX_OPPORTUNITY"] + min(abs(change_pct) * 3, 30)
                opps.append(Opportunity(
                    detected_at=now,
                    category="FX_OPPORTUNITY",
                    title=f"Naira {direction} {abs(change_pct):.1f}%: ₦{current_rate:,.0f}/USD",
                    description=(
                        f"USD/NGN moved from ₦{prev_rate:,.0f} to ₦{current_rate:,.0f} ({change_pct:+.1f}%). "
                        f"{'Naira weakness: dollar-denominated assets (Rise, Bamboo USD) gaining value.' if change_pct > 0 else 'Naira strength: good time to convert USD earnings.'}"
                    ),
                    score=min(score, 100),
                    alert_level=_alert_level(min(score, 100)),
                    source="CBN",
                ))
    return opps
