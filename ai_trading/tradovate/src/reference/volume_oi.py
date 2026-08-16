"""CME Volume & Open Interest fetching + parsing (§4).

Split deliberately: `parse_volume_payload` is pure and fully tested;
`CMEVolumeFetcher` does the network I/O and is exercised only at deployment.

DEPLOYMENT NOTE — needs live verification: CME aggressively blocks
datacenter/cloud IPs for scraping (confirmed during development), so the
exact JSON field names of the volume XHR must be confirmed from a
residential/deployment network before Phase 8. The parser below accepts the
commonly observed shapes and raises VolumeFetchError loudly on anything it
does not recognize — the resolver then refuses to trade on stale data (§4),
which is the designed failure mode.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

# CME contract month letters, Jan → Dec
MONTH_CODES = "FGHJKMNQUVXZ"
MONTH_NAMES = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUNE": 6,
    "JUL": 7, "JLY": 7, "JULY": 7, "AUG": 8, "SEP": 9, "SEPT": 9, "OCT": 10,
    "NOV": 11, "DEC": 12,
}


class VolumeFetchError(Exception):
    pass


@dataclass(frozen=True)
class ContractVolumeOI:
    product: str            # 'MES'
    contract_code: str      # 'MESU6'
    contract_month: str     # 'SEP 2026' (normalized)
    trade_date: str         # 'YYYY-MM-DD' (CME data date)
    volume: int
    open_interest: int


def month_to_code(month_label: str) -> tuple[str, str]:
    """'SEP 2026' / 'SEP 26' / 'JLY 25' → ('U6', 'SEP 2026')."""
    m = re.match(r"([A-Za-z]+)\s+(\d{2,4})", month_label.strip())
    if not m:
        raise VolumeFetchError(f"unparseable contract month: {month_label!r}")
    name, year_s = m.group(1).upper(), m.group(2)
    if name not in MONTH_NAMES:
        raise VolumeFetchError(f"unknown contract month name: {month_label!r}")
    month_num = MONTH_NAMES[name]
    year = int(year_s) if len(year_s) == 4 else 2000 + int(year_s)
    code = f"{MONTH_CODES[month_num - 1]}{year % 10}"
    normalized = f"{[k for k, v in MONTH_NAMES.items() if v == month_num][0]} {year}"
    return code, normalized


def _to_int(value) -> int:
    if value in (None, "", "-"):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return int(str(value).replace(",", "").strip() or 0)


def parse_volume_payload(product: str, payload: dict) -> list[ContractVolumeOI]:
    """Parse a CME volume JSON payload into per-contract records.

    Accepts the observed shapes: rows under 'monthData' (or 'rows'), with
    month label under 'month'/'monthID', volume under 'totalVolume'/'volume',
    open interest under 'openInterest'/'atClose'. Trade date under
    'tradeDate' (e.g. '2026-08-14' or '14 Aug 2026' → normalized best-effort).
    """
    rows = payload.get("monthData") or payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise VolumeFetchError(f"{product}: no monthData rows in volume payload")

    trade_date = str(payload.get("tradeDate", "")).strip()
    m = re.match(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", trade_date)
    if m:
        day, mon_name, year = m.groups()
        mon = MONTH_NAMES.get(mon_name.upper()[:3])
        if mon:
            trade_date = f"{year}-{mon:02d}-{int(day):02d}"
    if not re.match(r"\d{4}-\d{2}-\d{2}", trade_date):
        raise VolumeFetchError(f"{product}: unparseable tradeDate {trade_date!r}")

    records = []
    for row in rows:
        label = row.get("month") or row.get("monthID")
        if not label or str(label).strip().upper() in ("TOTAL", "TOTALS"):
            continue
        code_suffix, normalized = month_to_code(str(label))
        records.append(ContractVolumeOI(
            product=product,
            contract_code=f"{product}{code_suffix}",
            contract_month=normalized,
            trade_date=trade_date,
            volume=_to_int(row.get("totalVolume", row.get("volume"))),
            open_interest=_to_int(row.get("openInterest", row.get("atClose"))),
        ))
    if not records:
        raise VolumeFetchError(f"{product}: volume payload contained only totals")
    return records


class CMEVolumeFetcher:
    """Fetches the volume page/XHR for a product slug. Network-facing —
    verified at deployment (see module docstring)."""

    XHR_RE = re.compile(r"CmeWS/mvc/Volume/Details[^\"']*")

    def __init__(self, url_template: str, timeout: float = 20.0):
        self.url_template = url_template
        self.timeout = timeout

    def _get(self, url: str) -> str:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) tradovate-bot/0.1 reference-daemon",
            "Accept": "application/json, text/html",
        })
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def fetch(self, product: str, cme_slug: str) -> list[ContractVolumeOI]:
        page_url = self.url_template.format(cme_slug=cme_slug)
        body = self._get(page_url)
        # If the page embeds/links the volume XHR, follow it for clean JSON.
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            xhr = self.XHR_RE.search(body)
            if not xhr:
                raise VolumeFetchError(
                    f"{product}: volume page had no parseable JSON or XHR link")
            payload = json.loads(self._get("https://www.cmegroup.com/" + xhr.group(0)))
        return parse_volume_payload(product, payload)
