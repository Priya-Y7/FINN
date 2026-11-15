"""screener.in: links to annual reports and concall transcripts for any NSE ticker.

Tries the consolidated page first, then standalone. The HTML structure follows screener.in as I
know it (a documents section with annual-report and concall lists); the parser is tolerant and
returns whatever links it can classify.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from . import SourceError
from .http import get, new_session

BASE = "https://www.screener.in"


def company_page(ticker: str) -> tuple[str, str]:
    """Returns (url, html), trying consolidated then standalone."""
    session = new_session()
    last: Exception | None = None
    for variant in ("consolidated/", ""):
        url = f"{BASE}/company/{ticker.upper()}/{variant}"
        try:
            return url, get(url, session=session).text
        except SourceError as exc:
            last = exc
    raise SourceError(f"screener.in has no page for {ticker}: {last}")


def fetch_documents(ticker: str) -> dict:
    url, html = company_page(ticker)
    docs = parse_documents(html)
    docs["page_url"] = url
    return docs


def _abs(href: str) -> str:
    return href if href.startswith("http") else BASE + href


def parse_documents(html: str) -> dict:
    """Returns {'annual_reports': [{period, title, url}], 'transcripts': [{period, title, url}]}."""
    soup = BeautifulSoup(html, "html.parser")
    annual, transcripts = [], []

    section = soup.find(id="documents") or soup
    ar_box = section.find(class_=re.compile(r"annual-reports")) or _box_after_heading(section, "annual report")
    cc_box = section.find(class_=re.compile(r"concalls")) or _box_after_heading(section, "concall")

    if ar_box:
        for a in ar_box.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            match = re.search(r"(?:FY|Financial Year)\s*(\d{4})", text, flags=re.IGNORECASE)
            annual.append({"period": f"FY{match.group(1)}" if match else text, "title": text, "url": _abs(a["href"])})

    if cc_box:
        for li in cc_box.find_all("li"):
            period_match = re.search(r"[A-Z][a-z]{2}\s+\d{4}", li.get_text(" ", strip=True))
            period = period_match.group(0) if period_match else ""
            for a in li.find_all("a", href=True):
                label = a.get_text(" ", strip=True)
                if "transcript" in label.lower():
                    transcripts.append({"period": period, "title": f"Concall transcript {period}".strip(), "url": _abs(a["href"])})

    return {"annual_reports": annual, "transcripts": transcripts}


def _box_after_heading(root, keyword: str):
    for h in root.find_all(["h3", "h4", "h5", "div", "span"]):
        if h.get_text(strip=True).lower().startswith(keyword):
            nxt = h.find_next(["ul", "div"])
            if nxt:
                return nxt
    return None
