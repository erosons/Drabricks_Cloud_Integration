import logging
import re
from datetime import datetime
from typing import List

from config import SCRAPE_URLS, WAT
from scrapers.base import BaseScraper
from storage.models import PolicyEvent

log = logging.getLogger(__name__)

# Known current MPR — used as seed if scraping yields nothing
_KNOWN_MPR = 27.5
_KNOWN_CRR = 45.0


class CBNScraper(BaseScraper):
    def __init__(self):
        super().__init__("CBN")

    def scrape(self) -> List[PolicyEvent]:
        events: List[PolicyEvent] = []
        events.extend(self._scrape_mpr())
        events.extend(self._scrape_fx())
        events.extend(self._scrape_press_releases())
        log.info("CBN: %d policy events", len(events))
        return events

    # ── MPR ───────────────────────────────────────────────────────────────────

    def _scrape_mpr(self) -> List[PolicyEvent]:
        now = datetime.now(WAT)
        resp = self.get_first([
            SCRAPE_URLS["cbn_mpc"],
            SCRAPE_URLS["cbn_mpc_alt"],
            SCRAPE_URLS["cbn_home"],
        ])
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml") if resp else None

        mpr = _KNOWN_MPR
        crr = _KNOWN_CRR

        if soup:
            text = soup.get_text()
            # Look for MPR pattern e.g. "MPR at 27.50%" or "Monetary Policy Rate of 27.5"
            for pattern in [
                r"MPR\s*(?:at|to|of)?\s*([\d.]+)\s*%",
                r"Monetary Policy Rate\s*(?:at|to|of)?\s*([\d.]+)\s*%",
                r"policy rate\s*(?:at|to|of)?\s*([\d.]+)\s*%",
            ]:
                m = re.search(pattern, text, re.I)
                if m:
                    mpr = float(m.group(1))
                    break

            for pattern in [
                r"CRR\s*(?:at|to|of)?\s*([\d.]+)\s*%",
                r"Cash Reserve Ratio\s*(?:at|to|of)?\s*([\d.]+)\s*%",
            ]:
                m = re.search(pattern, text, re.I)
                if m:
                    crr = float(m.group(1))
                    break

        return [
            PolicyEvent(
                timestamp=now,
                event_type="MPR",
                title=f"CBN Monetary Policy Rate: {mpr}%",
                value=mpr,
                description=f"Current MPR is {mpr}%. CRR: {crr}%.",
                source="CBN",
                url=SCRAPE_URLS["cbn_mpc"],
            ),
            PolicyEvent(
                timestamp=now,
                event_type="CRR",
                title=f"CBN Cash Reserve Ratio: {crr}%",
                value=crr,
                description=f"Current CRR is {crr}%.",
                source="CBN",
                url=SCRAPE_URLS["cbn_mpc"],
            ),
        ]

    # ── FX Rates ──────────────────────────────────────────────────────────────

    def _scrape_fx(self) -> List[PolicyEvent]:
        now = datetime.now(WAT)
        events = []

        resp = self.get_first([SCRAPE_URLS["cbn_rates"], SCRAPE_URLS["cbn_rates_alt"], SCRAPE_URLS["cbn_home"]])
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml") if resp else None
        if soup is None:
            return events

        text = soup.get_text()
        # Look for USD/NGN rate
        for pattern in [
            r"USD\s*/\s*NGN\s*[\-:]\s*([\d,]+\.?\d*)",
            r"1\s*USD\s*=\s*([\d,]+\.?\d*)\s*(?:NGN|Naira)",
            r"Dollar\s*(?:rate|exchange)\s*(?:of|at|:)?\s*₦?([\d,]+\.?\d*)",
        ]:
            m = re.search(pattern, text, re.I)
            if m:
                rate = self.safe_float(m.group(1))
                if rate and rate > 100:  # sanity check
                    events.append(PolicyEvent(
                        timestamp=now,
                        event_type="FX_RATE",
                        title=f"CBN Official USD/NGN Rate: ₦{rate:,.2f}",
                        value=rate,
                        description=f"Official exchange rate: 1 USD = ₦{rate:,.2f}",
                        source="CBN",
                        url=SCRAPE_URLS["cbn_rates"],
                    ))
                break

        return events

    # ── Press Releases ────────────────────────────────────────────────────────

    def _scrape_press_releases(self) -> List[PolicyEvent]:
        now = datetime.now(WAT)
        events = []
        resp = self.get_first([SCRAPE_URLS["cbn_press"], SCRAPE_URLS["cbn_press_alt"], SCRAPE_URLS["cbn_home"]])
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml") if resp else None
        if soup is None:
            return events

        # Find links on press release page
        items = soup.select("a[href]")
        count = 0
        for a in items:
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            # Filter for recent relevant releases
            if any(kw in title.lower() for kw in [
                "monetary", "mpc", "interest", "inflation", "rate", "policy",
                "forex", "naira", "bond", "treasury", "budget", "fiscal",
            ]):
                if not href.startswith("http"):
                    href = "https://www.cbn.gov.ng" + href
                events.append(PolicyEvent(
                    timestamp=now,
                    event_type="PRESS_RELEASE",
                    title=title[:200],
                    description="CBN Press Release",
                    url=href,
                    source="CBN",
                ))
                count += 1
                if count >= 10:
                    break

        return events


def run() -> List[PolicyEvent]:
    return CBNScraper().scrape()
