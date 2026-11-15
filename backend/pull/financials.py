"""Structured financials: parse screener.in tables, store, read back as DataFrames. Units: rupees crore."""
from __future__ import annotations

import re

import pandas as pd
from bs4 import BeautifulSoup

from .. import db
from ..sources import SourceError, screener
from .periods import parse_period_end

# screener row label (lower-case, "+" stripped) -> our metric. Sections: profit-loss, quarters, balance-sheet, cash-flow, ratios
LABELS = {
    "sales": "sales", "revenue": "sales", "operating profit": "operating_profit", "net profit": "pat",
    "borrowings": "borrowings", "equity capital": "equity_capital", "reserves": "reserves",
    "cash from operating activity": "cfo", "fixed assets purchased": "capex",
    "debtor days": "debtor_days", "inventory days": "inventory_days", "days payable": "payable_days",
    "roce %": "roce_pct", "interest": "interest", "depreciation": "depreciation",
}
SECTIONS = {"quarters": "Q", "profit-loss": "A", "balance-sheet": "A", "cash-flow": "A", "ratios": "A"}


def _num(text: str) -> float | None:
    t = (text or "").replace(",", "").replace("%", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def parse_tables(html: str) -> list[dict]:
    """Returns rows {freq, period_end 'YYYY-MM', metric, value}. Tolerant: unknown rows are skipped."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for sec_id, freq in SECTIONS.items():
        sec = soup.find(id=sec_id)
        table = sec.find("table") if sec else None
        if not table:
            continue
        head = [th.get_text(" ", strip=True) for th in table.find("thead").find_all("th")] if table.find("thead") else []
        periods = [parse_period_end(h) for h in head[1:]]
        for tr in table.find("tbody").find_all("tr") if table.find("tbody") else []:
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if not cells:
                continue
            label = re.sub(r"[+\s]+$", "", cells[0]).lower()
            metric = LABELS.get(label)
            if not metric:
                continue
            for p, c in zip(periods, cells[1:]):
                v = _num(c)
                if p and v is not None:
                    out.append({"freq": freq, "period_end": f"{p[0]}-{p[1]:02d}", "metric": metric, "value": v})
    return out


def save(conn, ticker: str, rows: list[dict], is_sample: bool = False) -> int:
    conn.executemany(
        """INSERT INTO financials(ticker,freq,period_end,metric,value,is_sample) VALUES (?,?,?,?,?,?)
           ON CONFLICT(ticker,freq,period_end,metric) DO UPDATE SET value=excluded.value, is_sample=excluded.is_sample""",
        [(ticker, r["freq"], r["period_end"], r["metric"], r["value"], int(is_sample)) for r in rows])
    return len(rows)


def fetch_and_store(ticker: str) -> dict:
    url, html = screener.company_page(ticker)
    rows = parse_tables(html)
    if not rows:
        raise SourceError(f"no financial tables parsed for {ticker} ({url})")
    with db.session() as conn:
        n = save(conn, ticker, rows)
    return {"rows": n, "url": url, "consolidated": "/consolidated/" in url}


def load(conn, ticker: str, freq: str = "A") -> pd.DataFrame:
    """Wide frame indexed by period_end, one column per metric, oldest first."""
    rows = conn.execute("SELECT period_end, metric, value FROM financials WHERE ticker=? AND freq=?", (ticker, freq)).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows]).pivot(index="period_end", columns="metric", values="value").sort_index()
    if {"equity_capital", "reserves"} <= set(df.columns):
        df["equity"] = df["equity_capital"] + df["reserves"]
    return df
