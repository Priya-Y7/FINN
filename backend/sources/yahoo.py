"""End-of-day prices and volume from Yahoo Finance via yfinance (Indian tickers use .NS)."""
from __future__ import annotations

import pandas as pd

from . import SourceError
from .http import snapshot_only
from .. import config


def fetch_history(yahoo_symbol: str, period: str | None = None) -> pd.DataFrame:
    """Daily OHLCV with split/dividend-adjusted prices, columns: date, open, high, low, close, volume."""
    if snapshot_only():
        raise SourceError("USE_SNAPSHOT_ONLY is set: live sources are disabled")
    import yfinance as yf  # late import keeps tests and sample mode light

    period = period or config.settings()["prices"]["history_period"]
    try:
        raw = yf.Ticker(yahoo_symbol).history(period=period, interval="1d", auto_adjust=True)
    except Exception as exc:  # noqa: BLE001  yfinance raises many kinds of errors
        raise SourceError(f"yfinance failed for {yahoo_symbol}: {exc}") from exc
    return normalise_history(raw, yahoo_symbol)


def normalise_history(raw: pd.DataFrame, label: str = "") -> pd.DataFrame:
    if raw is None or raw.empty:
        raise SourceError(f"no price rows returned for {label}")
    df = raw.reset_index()
    date_col = "Date" if "Date" in df.columns else df.columns[0]
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d"),
        "open": df["Open"], "high": df["High"], "low": df["Low"],
        "close": df["Close"], "volume": df["Volume"],
    })
    out = out.dropna(subset=["close"]).drop_duplicates("date")
    if out.empty:
        raise SourceError(f"all price rows empty for {label}")
    return out.reset_index(drop=True)
