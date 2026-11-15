"""Deterministic SAMPLE data so the app can be run and tested without live sources.

Everything made here is synthetic: prices are a seeded random walk, announcements are generic
templates. Rows are flagged (meta data_mode='sample', announcements.is_sample=1) and the UI shows a
"Sample data" banner. Never mixed with live data: `generate` refuses to run over live rows unless forced.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .. import config, db, holdings
from .store import ann_id, save_announcements, save_prices

TEMPLATES = [
    ("Financial Results", "Outcome of Board Meeting: Unaudited financial results for the quarter"),
    ("Order Win", "Receipt of new order / contract"),
    ("Analyst/Investor Meet", "Schedule of analyst / institutional investor meet"),
    ("Dividend", "Board recommends dividend"),
    ("Management Change", "Change in senior management personnel"),
    ("Credit Rating", "Credit rating reaffirmed"),
    ("General", "Clarification on price movement"),
]


def last_trading_day(today: datetime | None = None) -> pd.Timestamp:
    d = pd.Timestamp((today or datetime.now(timezone.utc)).date())
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d


def _seed(ticker: str) -> int:
    return int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16)


def _series(ticker: str, end: pd.Timestamp, days: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(_seed(ticker))
    dates = pd.bdate_range(end=end, periods=days)
    rets = rng.normal(0.0004, 0.014, days)
    vols = rng.lognormal(mean=13.5, sigma=0.25, size=days)
    # plant one price shock and one volume spike in the last 3 sessions for 4 stocks, so alerts have material
    pos = _seed(ticker) % 20
    if pos < 4:
        rets[-1 - pos % 3] += rng.choice([-1, 1]) * 0.06
        vols[-1 - pos % 3] *= 3.2
    price = 100 + (_seed(ticker) % 4000) * 0.5 * np.exp(np.cumsum(rets) - rets.sum())
    close = np.round(price, 2)
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": close * 0.998, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": np.round(vols),
    })


def generate(force: bool = False) -> dict:
    with db.session() as conn:
        mode = db.get_meta(conn, "data_mode")
        if mode == "live" and not force:
            raise RuntimeError("database holds live data; refusing to overwrite (pass force=True)")
        conn.execute("DELETE FROM announcements WHERE is_sample=1")
        end = last_trading_day()
        for c in config.all_companies():
            save_prices(conn, c["ticker"], _series(c["ticker"], end))
        holdings.compute_holdings(conn)
        items = []
        for c in config.all_companies():
            rng = np.random.default_rng(_seed(c["ticker"]) + 1)
            for k in range(int(rng.integers(1, 4))):
                cat, title = TEMPLATES[int(rng.integers(0, len(TEMPLATES)))]
                ts = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(
                    days=int(rng.integers(0, 6)), hours=int(rng.integers(0, 8)))
                items.append({"ticker": c["ticker"], "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                              "title": f"[SAMPLE] {title}", "category_text": cat, "pdf_url": None, "source": "sample"})
        n_ann = save_announcements(conn, items, is_sample=True)
        db.set_meta(conn, "data_mode", "sample")
        db.set_meta(conn, "prices_refreshed_at", db.now_iso())
        db.set_meta(conn, "announcements_refreshed_at", db.now_iso())
    from ..pull import sample_pull
    sample_pull.generate()
    from ..push import alerts, process
    process.run()
    alerts.evaluate()
    return {"companies": len(config.all_companies()), "announcements": n_ann, "as_of": str(end.date())}
