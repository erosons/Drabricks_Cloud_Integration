import logging
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import HEADERS

log = logging.getLogger(__name__)


class BaseScraper:
    """Shared session, retry logic, and HTML helpers for all scrapers."""

    def __init__(self, name: str, timeout: int = 20):
        self.name = name
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get(self, url: str, retries: int = 3, delay: float = 2.0,
            ssl_fallback: bool = True, **kwargs) -> Optional[requests.Response]:
        verify = kwargs.pop("verify", True)
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout, verify=verify, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.exceptions.SSLError as e:
                if ssl_fallback and verify:
                    log.debug("[%s] SSL error for %s, retrying without verify", self.name, url)
                    try:
                        import urllib3
                        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                        resp = self.session.get(url, timeout=self.timeout, verify=False, **kwargs)
                        resp.raise_for_status()
                        return resp
                    except requests.RequestException:
                        pass
                log.warning("[%s] attempt %d/%d SSL failed for %s: %s", self.name, attempt, retries, url, e)
                if attempt < retries:
                    time.sleep(delay * attempt)
            except requests.RequestException as e:
                log.warning("[%s] attempt %d/%d failed for %s: %s", self.name, attempt, retries, url, e)
                if attempt < retries:
                    time.sleep(delay * attempt)
        return None

    def get_first(self, urls: list, **kwargs) -> Optional[requests.Response]:
        """Try multiple URLs and return the first successful response."""
        for url in urls:
            resp = self.get(url, retries=1, delay=1.0, **kwargs)
            if resp is not None:
                return resp
        return None

    def soup(self, url: str, **kwargs) -> Optional[BeautifulSoup]:
        resp = self.get(url, **kwargs)
        if resp is None:
            return None
        return BeautifulSoup(resp.text, "lxml")

    def safe_float(self, text: str) -> Optional[float]:
        if not text:
            return None
        cleaned = str(text).replace(",", "").replace("%", "").replace("₦", "").strip()
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    def safe_text(self, element) -> str:
        if element is None:
            return ""
        return element.get_text(strip=True)
