import logging
import re
from datetime import datetime
from typing import List

from config import SCRAPE_URLS, WAT
from scrapers.base import BaseScraper
from storage.models import IPO

log = logging.getLogger(__name__)


class SECNigeriaScraper(BaseScraper):
    def __init__(self):
        super().__init__("SEC-NG")

    def scrape(self) -> List[IPO]:
        now = datetime.now(WAT)
        ipos: List[IPO] = []
        ipos.extend(self._scrape_public_offers(now))
        ipos.extend(self._scrape_sec_news(now))
        log.info("SEC: %d IPO records", len(ipos))
        return ipos

    def _scrape_public_offers(self, now: datetime) -> List[IPO]:
        soup = self.soup(SCRAPE_URLS["sec_public_offers"])
        if soup is None:
            return []

        ipos = []
        # Try structured tables first
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).upper() for th in table.find_all("th")]
            if not any(h in headers for h in ("COMPANY", "OFFER", "IPO", "ISSUER")):
                continue
            for tr in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cells) < 2:
                    continue
                ipo = IPO(
                    scraped_at=now,
                    company=cells[0][:200],
                    status=self._infer_status(cells),
                    source="SEC-NG",
                    url=SCRAPE_URLS["sec_public_offers"],
                )
                if len(cells) > 1:
                    ipo.sector = cells[1][:100]
                for cell in cells:
                    price = self.safe_float(re.sub(r"[₦N]", "", cell))
                    if price and 0.1 < price < 1_000_000:
                        ipo.offer_price = price
                        break
                # Look for dates
                for cell in cells:
                    m = re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", cell)
                    if m and not ipo.opening_date:
                        ipo.opening_date = m.group(0)
                ipos.append(ipo)

        # Fallback: look for offer items in article/card format
        if not ipos:
            for card in soup.select("article, .offer-item, .card, .post"):
                title_el = card.find(["h2", "h3", "h4", "a"])
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not any(kw in title.lower() for kw in ["ipo", "offer", "shares", "bond", "listing"]):
                    continue
                href = title_el.get("href", "") if title_el.name == "a" else ""
                if href and not href.startswith("http"):
                    href = "https://www.sec.gov.ng" + href
                ipos.append(IPO(
                    scraped_at=now,
                    company=title[:200],
                    status="UPCOMING",
                    source="SEC-NG",
                    url=href or SCRAPE_URLS["sec_public_offers"],
                ))

        return ipos[:20]

    def _scrape_sec_news(self, now: datetime) -> List[IPO]:
        soup = self.soup(SCRAPE_URLS["sec_news"])
        if soup is None:
            return []
        ipos = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if any(kw in text.lower() for kw in ["ipo", "public offer", "rights issue", "listing"]):
                href = a["href"]
                if not href.startswith("http"):
                    href = "https://www.sec.gov.ng" + href
                ipos.append(IPO(
                    scraped_at=now,
                    company=text[:200],
                    status="UPCOMING",
                    source="SEC-NG-News",
                    url=href,
                ))
                if len(ipos) >= 10:
                    break
        return ipos

    def _infer_status(self, cells: list) -> str:
        text = " ".join(cells).lower()
        if "open" in text or "ongoing" in text or "current" in text:
            return "OPEN"
        if "upcoming" in text or "forthcoming" in text:
            return "UPCOMING"
        if "closed" in text or "completed" in text or "alloted" in text:
            return "CLOSED"
        return "UPCOMING"


def run() -> List[IPO]:
    return SECNigeriaScraper().scrape()
