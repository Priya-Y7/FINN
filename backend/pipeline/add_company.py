"""Add any NSE-listed company on demand, so research is not limited to the demo set."""
from __future__ import annotations

import re

from .. import config, db
from ..sources import SourceError, yahoo
from .store import save_prices

VALID = re.compile(r"^[A-Z0-9&\-]{1,20}$")


def normalise_ticker(raw: str) -> str:
    return re.sub(r"\.(NS|BO)$", "", (raw or "").strip().upper())


def _profile(symbol: str) -> tuple[str | None, str | None]:
    """Company name and sector from Yahoo, best effort (never fails the add)."""
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        return info.get("longName") or info.get("shortName"), info.get("sector")
    except Exception:  # noqa: BLE001
        return None, None


def add(raw_ticker: str) -> dict:
    t = normalise_ticker(raw_ticker)
    if not VALID.match(t):
        raise SourceError(f"'{raw_ticker}' is not a valid NSE ticker")
    with db.session() as conn:
        row = conn.execute("SELECT ticker,name FROM companies WHERE ticker=?", (t,)).fetchone()
    if row:
        return {"ticker": row["ticker"], "name": row["name"], "added": False}
    symbol = config.yahoo_symbol(t)
    try:
        df = yahoo.fetch_history(symbol)             # also proves the ticker exists on NSE
    except SourceError as exc:
        raise SourceError(f"Could not find NSE ticker {t}. Check the symbol (for example RELIANCE or TCS). {exc}") from exc
    name, sector = _profile(symbol)
    with db.session() as conn:
        conn.execute("""INSERT OR IGNORE INTO companies(ticker,yahoo_symbol,name,sector,size,is_bank,bse_code,in_portfolio,weight)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                     (t, symbol, name or t, sector or "Other", None, 1 if (sector or "") == "Financial Services" and "bank" in (name or "").lower() else 0, None, 0, 0))
        save_prices(conn, t, df)
    return {"ticker": t, "name": name or t, "added": True}
