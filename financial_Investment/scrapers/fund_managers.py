import logging
import re
from datetime import datetime
from typing import List, Tuple

from config import SCRAPE_URLS, WAT
from scrapers.base import BaseScraper
from storage.models import FundRate

log = logging.getLogger(__name__)

# Fallback seed rates (approximate current market offerings, June 2026)
_SEED_RATES: List[Tuple] = [
    # (provider, product, rate, rate_label, currency, duration, min_amount, description)
    ("Rise", "Stock (USD)", None, "Market returns", "USD", "Long-term", 10.0, "US & Nigerian stocks"),
    ("Rise", "Real Estate (USD)", None, "15-25% p.a. est.", "USD", "12-24 months", 100.0, "US real estate"),
    ("Rise", "Fixed Income (USD)", 9.0, "9% p.a.", "USD", "6-12 months", 10.0, "USD fixed income"),
    ("PiggyVest", "PiggyBank (NGN)", 10.0, "10% p.a.", "NGN", "Any term", 100.0, "Flexible savings"),
    ("PiggyVest", "Flex Dollar", 7.0, "7% p.a.", "USD", "Flexible", 1.0, "Dollar savings"),
    ("PiggyVest", "SafeLock (NGN)", 13.0, "13% p.a.", "NGN", "Locked", 100.0, "Locked savings"),
    ("PiggyVest", "Investify", None, "Variable", "NGN", "Variable", 1000.0, "Mutual funds"),
    ("Bamboo", "Stocks (NGN)", None, "Market returns", "NGN", "Any", 1000.0, "Nigerian equities via NGX"),
    ("Bamboo", "Stocks (USD)", None, "Market returns", "USD", "Any", 1.0, "US equities"),
    ("Bamboo", "Fixed Income", 18.0, "~18% p.a.", "NGN", "Fixed", 10000.0, "Nigerian fixed income"),
    ("Afriinvest", "Money Market Fund", 22.0, "~22% p.a.", "NGN", "Liquid", 5000.0, "Liquid money market"),
    ("Afriinvest", "Fixed Income Fund", 20.0, "~20% p.a.", "NGN", "Fixed", 10000.0, "FGN bonds & T-Bills"),
    ("Afriinvest", "Equity Fund", None, "Market returns", "NGN", "Long-term", 10000.0, "Nigerian equities"),
    ("CowryWise", "Savings Plan", 15.0, "up to 15% p.a.", "NGN", "Flexible", 100.0, "Automated savings"),
    ("CowryWise", "Investment Plan", 17.0, "up to 17% p.a.", "NGN", "Fixed", 1000.0, "Managed investments"),
    ("CowryWise", "Dollar Savings", 8.0, "up to 8% p.a.", "USD", "Flexible", 1.0, "USD savings"),
]


class FundManagerScraper(BaseScraper):
    def __init__(self):
        super().__init__("FundManagers")

    def scrape(self) -> List[FundRate]:
        now = datetime.now(WAT)
        rates: List[FundRate] = []

        rates.extend(self._scrape_rise(now))
        rates.extend(self._scrape_piggyvest(now))
        rates.extend(self._scrape_bamboo(now))
        rates.extend(self._scrape_afriinvest(now))
        rates.extend(self._scrape_cowrywise(now))

        # If we got nothing from live scraping, use seeds
        if not rates:
            log.warning("All fund managers fell back to seed data")
            rates = self._build_seeds(now)

        log.info("Fund managers: %d rate records", len(rates))
        return rates

    def _build_seeds(self, now: datetime) -> List[FundRate]:
        return [
            FundRate(
                timestamp=now, provider=p, product=prod, rate=rate,
                rate_label=label, currency=curr, duration=dur,
                min_amount=min_amt, description=desc,
            )
            for p, prod, rate, label, curr, dur, min_amt, desc in _SEED_RATES
        ]

    # ── Rise ──────────────────────────────────────────────────────────────────

    def _scrape_rise(self, now: datetime) -> List[FundRate]:
        soup = self.soup(SCRAPE_URLS["rise"])
        rates = []
        if soup is None:
            return self._seed_for("Rise", now)

        text = soup.get_text(" ", strip=True)
        # Rise typically shows "X% returns" on landing page
        patterns = [
            (r"(\d+(?:\.\d+)?)\s*%\s*(?:p\.a\.|per\s*(?:annum|year)|annual|returns?)", "Fixed Income (USD)", "USD"),
            (r"earn\s*(?:up\s*to\s*)?(\d+(?:\.\d+)?)\s*%", "Savings (USD)", "USD"),
        ]
        for pattern, product, curr in patterns:
            m = re.search(pattern, text, re.I)
            if m:
                rate = float(m.group(1))
                if 1 <= rate <= 50:
                    rates.append(FundRate(
                        timestamp=now, provider="Rise", product=product,
                        rate=rate, rate_label=f"{rate}% p.a.",
                        currency=curr, source_url=SCRAPE_URLS["rise"],
                    ))

        return rates or self._seed_for("Rise", now)

    # ── PiggyVest ─────────────────────────────────────────────────────────────

    def _scrape_piggyvest(self, now: datetime) -> List[FundRate]:
        soup = self.soup(SCRAPE_URLS["piggyvest"])
        rates = []
        if soup is None:
            return self._seed_for("PiggyVest", now)

        text = soup.get_text(" ", strip=True)
        for pattern in [
            r"(\d+(?:\.\d+)?)\s*%\s*(?:per\s*(?:annum|year)|p\.a\.|interest|returns?)",
            r"earn\s*(?:up\s*to\s*)?(\d+(?:\.\d+)?)\s*%",
        ]:
            for m in re.finditer(pattern, text, re.I):
                rate = float(m.group(1))
                if 1 <= rate <= 50:
                    context = text[max(0, m.start() - 30):m.end() + 30].lower()
                    curr = "USD" if "dollar" in context or "usd" in context or "$" in context else "NGN"
                    product = "Flex Dollar" if curr == "USD" else "Savings"
                    rates.append(FundRate(
                        timestamp=now, provider="PiggyVest", product=product,
                        rate=rate, rate_label=f"{rate}% p.a.", currency=curr,
                    ))
                    break

        return rates or self._seed_for("PiggyVest", now)

    # ── Bamboo ────────────────────────────────────────────────────────────────

    def _scrape_bamboo(self, now: datetime) -> List[FundRate]:
        soup = self.soup(SCRAPE_URLS["bamboo"])
        if soup is None:
            return self._seed_for("Bamboo", now)
        text = soup.get_text(" ", strip=True)
        rates = []
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%\s*(?:p\.a\.|per\s*(?:annum|year)|returns?|interest)", text, re.I):
            rate = float(m.group(1))
            if 1 <= rate <= 50:
                rates.append(FundRate(
                    timestamp=now, provider="Bamboo", product="Fixed Income",
                    rate=rate, rate_label=f"{rate}% p.a.", currency="NGN",
                ))
                break
        return rates or self._seed_for("Bamboo", now)

    # ── Afriinvest ────────────────────────────────────────────────────────────

    def _scrape_afriinvest(self, now: datetime) -> List[FundRate]:
        soup = self.soup(SCRAPE_URLS["afriinvest"])
        if soup is None:
            return self._seed_for("Afriinvest", now)
        rates = []
        text = soup.get_text(" ", strip=True)
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%\s*(?:p\.a\.|per\s*(?:annum|year)|returns?|yield)", text, re.I):
            rate = float(m.group(1))
            if 5 <= rate <= 50:
                rates.append(FundRate(
                    timestamp=now, provider="Afriinvest", product="Money Market Fund",
                    rate=rate, rate_label=f"{rate}% p.a.", currency="NGN",
                ))
                break
        return rates or self._seed_for("Afriinvest", now)

    # ── CowryWise ─────────────────────────────────────────────────────────────

    def _scrape_cowrywise(self, now: datetime) -> List[FundRate]:
        soup = self.soup(SCRAPE_URLS["cowrywise"])
        if soup is None:
            return self._seed_for("CowryWise", now)
        rates = []
        text = soup.get_text(" ", strip=True)
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%\s*(?:p\.a\.|per\s*(?:annum|year)|returns?|interest)", text, re.I):
            rate = float(m.group(1))
            if 1 <= rate <= 50:
                context = text[max(0, m.start()-30):m.end()+30].lower()
                curr = "USD" if ("dollar" in context or "usd" in context) else "NGN"
                rates.append(FundRate(
                    timestamp=now, provider="CowryWise",
                    product="Dollar Savings" if curr == "USD" else "Investment Plan",
                    rate=rate, rate_label=f"{rate}% p.a.", currency=curr,
                ))
        return rates or self._seed_for("CowryWise", now)

    def _seed_for(self, provider: str, now: datetime) -> List[FundRate]:
        return [
            FundRate(
                timestamp=now, provider=p, product=prod, rate=rate,
                rate_label=label, currency=curr, duration=dur,
                min_amount=min_amt, description=desc,
            )
            for p, prod, rate, label, curr, dur, min_amt, desc in _SEED_RATES
            if p == provider
        ]


def run() -> List[FundRate]:
    return FundManagerScraper().scrape()
