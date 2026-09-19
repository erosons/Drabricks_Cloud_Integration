import logging
import re
from datetime import datetime
from typing import List

import feedparser
from dateutil import parser as dateparser

from config import SCRAPE_URLS, WAT, SENTIMENT_POSITIVE, SENTIMENT_NEGATIVE, POLICY_KEYWORDS
from scrapers.base import BaseScraper
from storage.models import NewsArticle

log = logging.getLogger(__name__)

RSS_SOURCES = [
    ("Nairametrics", SCRAPE_URLS["nairametrics_rss"]),
    ("BusinessDay NG", SCRAPE_URLS["businessday_rss"]),
    ("Proshare", SCRAPE_URLS["proshare_rss"]),
    ("The Guardian NG", SCRAPE_URLS["guardian_ng_rss"]),
]

FINANCE_KEYWORDS = [
    "stock", "equity", "share", "nse", "ngx", "bond", "treasury", "t-bill",
    "naira", "dollar", "forex", "cbn", "dmo", "sec", "interest rate", "inflation",
    "investment", "fund", "ipo", "listing", "dividend", "profit", "earnings",
    "budget", "fiscal", "monetary", "mpc", "bank", "finance", "economy", "gdp",
    "oil", "gas", "fgn", "pension", "insurance", "capital market",
]


class NewsScraper(BaseScraper):
    def __init__(self):
        super().__init__("News")

    def scrape(self) -> List[NewsArticle]:
        now = datetime.now(WAT)
        articles: List[NewsArticle] = []

        for source_name, url in RSS_SOURCES:
            articles.extend(self._scrape_rss(source_name, url, now))

        articles.extend(self._scrape_proshare_html(now))

        log.info("News: %d articles", len(articles))
        return articles

    def _scrape_rss(self, source: str, url: str, now: datetime) -> List[NewsArticle]:
        articles = []
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:30]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                # Filter for financial relevance
                combined = (title + " " + entry.get("summary", "")).lower()
                if not any(kw in combined for kw in FINANCE_KEYWORDS):
                    continue

                pub_dt = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        pub_dt = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass
                if pub_dt is None:
                    pub_dt = now

                summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:500]
                url_link = entry.get("link", "")

                article = NewsArticle(
                    scraped_at=now,
                    source=source,
                    title=title[:300],
                    summary=summary,
                    url=url_link,
                    published_at=pub_dt,
                    category=self._classify_category(title + " " + summary),
                    sentiment=self._score_sentiment(title + " " + summary),
                    tags=self._extract_tags(title + " " + summary),
                )
                articles.append(article)
        except Exception as e:
            log.warning("[%s] RSS parse error: %s", source, e)
        return articles

    def _scrape_proshare_html(self, now: datetime) -> List[NewsArticle]:
        articles = []
        soup = self.soup(SCRAPE_URLS["proshare_home"])
        if soup is None:
            return articles

        for a in soup.select("a[href]"):
            title = a.get_text(strip=True)
            if len(title) < 20:
                continue
            combined = title.lower()
            if not any(kw in combined for kw in FINANCE_KEYWORDS):
                continue
            href = a["href"]
            if not href.startswith("http"):
                href = "https://proshareng.com" + href
            articles.append(NewsArticle(
                scraped_at=now,
                source="Proshare",
                title=title[:300],
                url=href,
                published_at=now,
                category=self._classify_category(title),
                sentiment=self._score_sentiment(title),
            ))
            if len(articles) >= 20:
                break
        return articles

    def _classify_category(self, text: str) -> str:
        text = text.lower()
        scores = {}
        for cat, keywords in POLICY_KEYWORDS.items():
            scores[cat] = sum(1 for kw in keywords if kw in text)

        # Map to dashboard categories
        best = max(scores, key=scores.get) if scores else "economy"
        if scores.get(best, 0) == 0:
            if any(kw in text for kw in ["stock", "equity", "share", "ngx", "nse"]):
                return "STOCKS"
            return "GENERAL"

        mapping = {
            "fiscal": "POLICY",
            "monetary": "POLICY",
            "fx": "FOREX",
            "investment": "TREASURY",
            "economy": "GENERAL",
        }
        return mapping.get(best, "GENERAL")

    def _score_sentiment(self, text: str) -> float:
        words = re.findall(r"\b\w+\b", text.lower())
        if not words:
            return 0.0
        pos = sum(1 for w in words if w in SENTIMENT_POSITIVE)
        neg = sum(1 for w in words if w in SENTIMENT_NEGATIVE)
        total = len(words)
        return round((pos - neg) / max(total, 1) * 10, 3)  # scaled -1 to 1 approx

    def _extract_tags(self, text: str) -> str:
        text_lower = text.lower()
        found = []
        tag_map = {
            "NGX": ["ngx", "nse", "stock exchange"],
            "CBN": ["cbn", "central bank"],
            "MPR": ["mpr", "monetary policy rate"],
            "TBILL": ["t-bill", "treasury bill"],
            "BOND": ["bond", "fgn bond"],
            "IPO": ["ipo", "public offer"],
            "NAIRA": ["naira", "ngn"],
            "FOREX": ["forex", "fx", "exchange rate"],
            "INFLATION": ["inflation"],
            "OIL": ["oil", "petroleum", "nnpc"],
            "PENSION": ["pension", "pencom"],
        }
        for tag, kws in tag_map.items():
            if any(kw in text_lower for kw in kws):
                found.append(tag)
        return ",".join(found[:5])


def run() -> List[NewsArticle]:
    return NewsScraper().scrape()
