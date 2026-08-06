import io
import logging
import re
from datetime import datetime
from typing import List, Tuple

import pandas as pd

from config import SCRAPE_URLS, WAT
from scrapers.base import BaseScraper
from storage.models import NGXIndex, NGXEquity

log = logging.getLogger(__name__)


class NGXScraper(BaseScraper):
    def __init__(self):
        super().__init__("NGX")

    def scrape(self) -> Tuple[NGXIndex, List[NGXEquity]]:
        now = datetime.now(WAT)
        index = self._scrape_index(now)
        equities = self._scrape_equities(now)
        log.info("NGX: index=%.2f, equities=%d", index.index_value, len(equities))
        return index, equities

    # ── Index ─────────────────────────────────────────────────────────────────

    def _scrape_index(self, now: datetime) -> NGXIndex:
        soup = self.soup(SCRAPE_URLS["ngx_home"])
        idx = NGXIndex(timestamp=now)

        if soup is None:
            return idx

        # NGX homepage — look for the All-Share Index value in common patterns
        for selector in [
            {"string": re.compile(r"All.Share", re.I)},
            {"class_": re.compile(r"index|market.cap|asi", re.I)},
        ]:
            el = soup.find(attrs=selector)
            if el:
                parent = el.find_parent()
                nums = re.findall(r"[\d,]+\.?\d*", parent.get_text() if parent else "")
                if nums:
                    idx.index_value = self.safe_float(nums[0]) or 0.0
                    break

        # Try JSON endpoint many Nigerian financial sites expose
        resp = self.get(SCRAPE_URLS.get("ngx_api_equities", ""), retries=1) if SCRAPE_URLS.get("ngx_api_equities") else None
        if resp and resp.headers.get("content-type", "").startswith("application/json"):
            try:
                data = resp.json()
                if isinstance(data, dict) and "allShareIndex" in data:
                    idx.index_value = float(data["allShareIndex"])
                    idx.change_pct = float(data.get("changePercent", 0))
                    idx.market_cap = float(data.get("marketCap", 0))
            except Exception:
                pass

        return idx

    # ── Equities ──────────────────────────────────────────────────────────────

    def _scrape_equities(self, now: datetime) -> List[NGXEquity]:
        equities: List[NGXEquity] = []

        # Attempt 1: CSV/Excel download from market data page
        resp = self.get(SCRAPE_URLS["ngx_market_data"])
        if resp:
            ct = resp.headers.get("content-type", "")
            if "csv" in ct or "excel" in ct or "spreadsheet" in ct or "octet" in ct:
                equities = self._parse_csv(resp.content, now)

        # Attempt 2: HTML table on the same page
        if not equities and resp:
            equities = self._parse_html_table(resp.text, now)

        # Attempt 3: Fallback — parse any downloadable link on the page
        if not equities:
            equities = self._find_and_download_csv(now)

        return equities

    def _parse_csv(self, content: bytes, now: datetime) -> List[NGXEquity]:
        equities = []
        try:
            df = pd.read_csv(io.BytesIO(content))
            df.columns = [c.strip().upper() for c in df.columns]
            col_map = {
                "SYMBOL": "symbol", "COMPANY": "name", "CLOSE": "price",
                "CHANGE(%)": "change_pct", "OPEN": "open_price",
                "HIGH": "high_price", "LOW": "low_price", "VOLUME": "volume",
                "DEALS": "deals", "SECTOR": "sector",
            }
            for _, row in df.iterrows():
                eq = NGXEquity(timestamp=now, symbol=str(row.get("SYMBOL", "")).strip())
                for col, attr in col_map.items():
                    if col in df.columns:
                        val = row.get(col)
                        if attr in ("symbol", "name", "sector"):
                            setattr(eq, attr, str(val).strip() if pd.notna(val) else "")
                        else:
                            setattr(eq, attr, self.safe_float(str(val)) or 0.0)
                if eq.symbol:
                    equities.append(eq)
        except Exception as e:
            log.debug("CSV parse failed: %s", e)
        return equities

    def _parse_html_table(self, html: str, now: datetime) -> List[NGXEquity]:
        from bs4 import BeautifulSoup
        equities = []
        soup = BeautifulSoup(html, "lxml")
        tables = soup.find_all("table")
        for table in tables:
            headers = [th.get_text(strip=True).upper() for th in table.find_all("th")]
            if not any(h in headers for h in ("SYMBOL", "CLOSE", "PRICE", "COMPANY")):
                continue
            for tr in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cells) < 3:
                    continue
                eq = NGXEquity(timestamp=now, symbol=cells[0] if cells else "")
                if len(cells) > 1:
                    eq.name = cells[1]
                if len(cells) > 2:
                    eq.price = self.safe_float(cells[2]) or 0.0
                if len(cells) > 3:
                    eq.change_pct = self.safe_float(cells[3]) or 0.0
                if eq.symbol:
                    equities.append(eq)
            if equities:
                break
        return equities

    def _find_and_download_csv(self, now: datetime) -> List[NGXEquity]:
        soup = self.soup(SCRAPE_URLS["ngx_market_data"])
        if soup is None:
            return []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(ext in href.lower() for ext in (".csv", ".xlsx", ".xls", "download", "export")):
                if not href.startswith("http"):
                    href = "https://ngxgroup.com" + href
                resp = self.get(href)
                if resp:
                    return self._parse_csv(resp.content, now)
        return []


def run() -> Tuple[NGXIndex, List[NGXEquity]]:
    return NGXScraper().scrape()
