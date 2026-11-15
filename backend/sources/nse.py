"""NSE corporate announcements.

NSE blocks plain scripts: it wants browser-like headers and a session cookie obtained by visiting
the site first. The field names below follow the NSE API as I know it; the parser is tolerant and
`python -m backend.cli verify-sources` shows exactly what comes back if something differs.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from . import SourceError
from .http import get, new_session

BASE = "https://www.nseindia.com"
IST = ZoneInfo("Asia/Kolkata")
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": BASE + "/companies-listing/corporate-filings-announcements",
}


class NseClient:
    def __init__(self) -> None:
        self.session = new_session(browser=True)
        self._primed = False

    def _prime(self) -> None:
        if not self._primed:
            get(BASE + "/", session=self.session)  # sets the cookies the API checks
            self._primed = True

    def announcements(self, symbol: str, from_date: datetime, to_date: datetime) -> list[dict]:
        self._prime()
        url = (f"{BASE}/api/corporate-announcements?index=equities&symbol={symbol}"
               f"&from_date={from_date:%d-%m-%Y}&to_date={to_date:%d-%m-%Y}")
        resp = get(url, session=self.session, headers=HEADERS)
        try:
            payload = resp.json()
        except ValueError as exc:
            raise SourceError("NSE returned non-JSON (likely blocked)") from exc
        return parse_announcements(payload, symbol)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%b-%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def parse_announcements(payload, ticker: str) -> list[dict]:
    """Normalise NSE rows to {ticker, ts (UTC ISO), title, category_text, pdf_url, source}."""
    items = payload if isinstance(payload, list) else (payload or {}).get("data", [])
    out = []
    for it in items:
        ts = _parse_ts(it.get("an_dt")) or _parse_ts(it.get("sort_date")) or _parse_ts(it.get("dt"))
        if ts is None:
            continue
        category = (it.get("desc") or "").strip()
        detail = (it.get("attchmntText") or "").strip()
        out.append({
            "ticker": ticker.upper(),
            "ts": ts.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "title": detail or category,
            "category_text": category,
            "pdf_url": (it.get("attchmntFile") or "").strip() or None,
            "source": "nse",
        })
    return out
