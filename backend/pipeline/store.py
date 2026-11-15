"""Shared write helpers for prices and announcements."""
from __future__ import annotations

import hashlib
import sqlite3

import pandas as pd

from .. import config
from ..metrics import add_metrics


def ann_id(ticker: str, ts: str, title: str) -> str:
    return hashlib.sha256(f"{ticker}|{ts}|{title}".encode()).hexdigest()[:20]


def save_prices(conn: sqlite3.Connection, ticker: str, df: pd.DataFrame) -> int:
    window = config.settings()["metrics"]["window_days"]
    m = add_metrics(df, window)
    rows = [
        (ticker, r.date, r.open, r.high, r.low, r.close, r.volume,
         None if pd.isna(r.ret_pct) else float(r.ret_pct),
         None if pd.isna(r.vol_ratio) else float(r.vol_ratio),
         None if pd.isna(r.z_ret) else float(r.z_ret))
        for r in m.itertuples(index=False)
    ]
    conn.executemany(
        """INSERT INTO prices(ticker,date,open,high,low,close,volume,ret_pct,vol_ratio,z_ret)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(ticker,date) DO UPDATE SET open=excluded.open, high=excluded.high, low=excluded.low,
             close=excluded.close, volume=excluded.volume, ret_pct=excluded.ret_pct,
             vol_ratio=excluded.vol_ratio, z_ret=excluded.z_ret""",
        rows,
    )
    return len(rows)


def save_announcements(conn: sqlite3.Connection, items: list[dict], is_sample: bool = False) -> int:
    n = 0
    for it in items:
        cur = conn.execute(
            """INSERT OR IGNORE INTO announcements(id,ticker,ts,source,title,category_text,pdf_url,is_sample)
               VALUES (?,?,?,?,?,?,?,?)""",
            (ann_id(it["ticker"], it["ts"], it["title"]), it["ticker"], it["ts"], it["source"],
             it["title"], it.get("category_text"), it.get("pdf_url"), 1 if is_sample else 0),
        )
        n += cur.rowcount
    return n
