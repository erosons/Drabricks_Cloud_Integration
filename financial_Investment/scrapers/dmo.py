import logging
import re
from datetime import datetime
from typing import List

from config import SCRAPE_URLS, WAT
from scrapers.base import BaseScraper
from storage.models import TreasuryRate

log = logging.getLogger(__name__)

# Seed data in case scraping fails — reflects approximate current market rates
_FALLBACK_TBILLS = [
    ("91-Day T-Bill", "91-day", 18.5),
    ("182-Day T-Bill", "182-day", 19.2),
    ("364-Day T-Bill", "364-day", 20.1),
]
_FALLBACK_BONDS = [
    ("FGN Bond 2yr", "2-year", 19.8),
    ("FGN Bond 5yr", "5-year", 20.5),
    ("FGN Bond 10yr", "10-year", 21.2),
    ("FGN Bond 20yr", "20-year", 21.8),
    ("FGN Bond 30yr", "30-year", 22.0),
]
_FALLBACK_SAVINGS = [
    ("FGN Savings Bond 2yr", "2-year", 13.0),
    ("FGN Savings Bond 3yr", "3-year", 14.0),
]


class DMOScraper(BaseScraper):
    def __init__(self):
        super().__init__("DMO")

    def scrape(self) -> List[TreasuryRate]:
        now = datetime.now(WAT)
        rates: List[TreasuryRate] = []
        rates.extend(self._scrape_tbills(now))
        rates.extend(self._scrape_bonds(now))
        rates.extend(self._scrape_savings_bonds(now))
        log.info("DMO: %d treasury rates", len(rates))
        return rates

    # ── T-Bills ───────────────────────────────────────────────────────────────

    def _scrape_tbills(self, now: datetime) -> List[TreasuryRate]:
        resp = self.get_first([SCRAPE_URLS["dmo_tbills"], SCRAPE_URLS["dmo_tbills_alt"], SCRAPE_URLS["dmo_home"]])
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml") if resp else None
        rates = self._parse_rate_tables(soup, "T-Bill", now)
        if not rates:
            log.warning("DMO T-Bills: falling back to seed data")
            rates = [
                TreasuryRate(timestamp=now, instrument=name, tenor=tenor, rate=rate, source="DMO-seed")
                for name, tenor, rate in _FALLBACK_TBILLS
            ]
        return rates

    # ── FGN Bonds ─────────────────────────────────────────────────────────────

    def _scrape_bonds(self, now: datetime) -> List[TreasuryRate]:
        resp = self.get_first([SCRAPE_URLS["dmo_bonds"], SCRAPE_URLS["dmo_bonds_alt"], SCRAPE_URLS["dmo_home"]])
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml") if resp else None
        rates = self._parse_rate_tables(soup, "FGN Bond", now)
        if not rates:
            log.warning("DMO Bonds: falling back to seed data")
            rates = [
                TreasuryRate(timestamp=now, instrument=name, tenor=tenor, rate=rate, source="DMO-seed")
                for name, tenor, rate in _FALLBACK_BONDS
            ]
        return rates

    # ── FGN Savings Bonds ─────────────────────────────────────────────────────

    def _scrape_savings_bonds(self, now: datetime) -> List[TreasuryRate]:
        soup = self.soup(SCRAPE_URLS["dmo_savings"])
        rates = self._parse_rate_tables(soup, "FGN Savings Bond", now)
        if not rates:
            rates = [
                TreasuryRate(timestamp=now, instrument=name, tenor=tenor, rate=rate, source="DMO-seed")
                for name, tenor, rate in _FALLBACK_SAVINGS
            ]
        return rates

    # ── Parser ────────────────────────────────────────────────────────────────

    def _parse_rate_tables(self, soup, label: str, now: datetime) -> List[TreasuryRate]:
        if soup is None:
            return []
        rates = []
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).upper() for th in table.find_all("th")]
            has_rate = any(kw in " ".join(headers) for kw in ("RATE", "YIELD", "INTEREST", "COUPON"))
            if not has_rate:
                continue

            for tr in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cells) < 2:
                    continue

                # Try to find a percentage value in any cell
                rate_val = None
                tenor_hint = ""
                name_hint = cells[0] if cells else ""

                for cell in cells:
                    # Look for tenor hint
                    m_tenor = re.search(r"(\d+)\s*-?\s*(day|year|yr|month|mo)", cell, re.I)
                    if m_tenor:
                        tenor_hint = m_tenor.group(0)

                    # Look for rate
                    m_rate = re.search(r"([\d.]+)\s*%", cell)
                    if m_rate:
                        candidate = float(m_rate.group(1))
                        if 1.0 <= candidate <= 50.0:  # sanity: 1–50% is reasonable
                            rate_val = candidate

                if rate_val is None:
                    # Try raw float in later columns
                    for cell in cells[1:]:
                        v = self.safe_float(cell)
                        if v and 1.0 <= v <= 50.0:
                            rate_val = v
                            break

                if rate_val is not None:
                    instrument = name_hint or f"{label} {tenor_hint}"
                    rates.append(TreasuryRate(
                        timestamp=now,
                        instrument=instrument[:100],
                        tenor=tenor_hint,
                        rate=rate_val,
                        source="DMO",
                    ))

        # Deduplicate by instrument name
        seen = set()
        unique = []
        for r in rates:
            if r.instrument not in seen:
                seen.add(r.instrument)
                unique.append(r)
        return unique


def run() -> List[TreasuryRate]:
    return DMOScraper().scrape()
