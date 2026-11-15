"""BSE corporate announcements, used as the fallback when NSE blocks us.

Needs the company's BSE scrip code (config bse_code). Field names follow the BSE API as I know it.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from . import SourceError
from .http import get, new_session

API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
ATTACH = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
IST = ZoneInfo("Asia/Kolkata")
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
}


def announcements(ticker: str, bse_code: str, from_date: datetime, to_date: datetime, max_pages: int = 3) -> list[dict]:
    if not bse_code:
        raise SourceError(f"no BSE code configured for {ticker}")
    session = new_session(browser=True)
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        url = (f"{API}?pageno={page}&strCat=-1&subcategory=-1&strPrevDate={from_date:%Y%m%d}"
               f"&strToDate={to_date:%Y%m%d}&strSearch=P&strscrip={bse_code}&strType=C")
        resp = get(url, session=session, headers=HEADERS)
        try:
            payload = resp.json()
        except ValueError as exc:
            raise SourceError("BSE returned non-JSON (likely blocked)") from exc
        rows = parse_announcements(payload, ticker)
        out.extend(rows)
        if len((payload or {}).get("Table", [])) < 50:   # last page
            break
    return out


def parse_announcements(payload, ticker: str) -> list[dict]:
    rows = (payload or {}).get("Table", []) if isinstance(payload, dict) else []
    out = []
    for it in rows:
        raw_ts = (it.get("NEWS_DT") or it.get("DissemDT") or "").split(".")[0]
        try:
            ts = datetime.strptime(raw_ts, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=IST)
        except ValueError:
            continue
        title = (it.get("NEWSSUB") or it.get("HEADLINE") or "").strip()
        attach = (it.get("ATTACHMENTNAME") or "").strip()
        out.append({
            "ticker": ticker.upper(),
            "ts": ts.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "title": title,
            "category_text": (it.get("CATEGORYNAME") or it.get("SUBCATNAME") or "").strip(),
            "pdf_url": (ATTACH + attach) if attach else None,
            "source": "bse",
        })
    return out
