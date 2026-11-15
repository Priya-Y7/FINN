"""Mock holdings (section 3.1).

    Qty_i    = (total value x weight_i) / close on the start date      (fixed afterwards)
    Value_i  = Qty_i x P_i,   Weight_i = Value_i / sum(Value_j)        (drifts as prices move)
    Impact_i = Qty_i x (P_t - P_t-1)
"""
from __future__ import annotations

import sqlite3

from . import config


def compute_holdings(conn: sqlite3.Connection) -> dict:
    """Set fixed quantities from the start-date close. Returns {'set': [...], 'skipped': [...]}."""
    cfg = config.settings()["holdings"]
    total, start = cfg["total_value_inr"], cfg["start_date"]
    done, skipped = [], []
    for c in config.portfolio():
        row = conn.execute(
            "SELECT date, close FROM prices WHERE ticker=? AND date>=? AND close IS NOT NULL ORDER BY date LIMIT 1",
            (c["ticker"], start),
        ).fetchone()
        if row is None:  # no price on/after start date: fall back to the earliest price we have
            row = conn.execute(
                "SELECT date, close FROM prices WHERE ticker=? AND close IS NOT NULL ORDER BY date LIMIT 1",
                (c["ticker"],),
            ).fetchone()
        if row is None:
            skipped.append(c["ticker"])
            continue
        qty = total * c["weight"] / 100.0 / row["close"]
        conn.execute(
            """INSERT INTO holdings(ticker, qty, start_date, start_price) VALUES (?,?,?,?)
               ON CONFLICT(ticker) DO UPDATE SET qty=excluded.qty, start_date=excluded.start_date,
                                                 start_price=excluded.start_price""",
            (c["ticker"], qty, row["date"], row["close"]),
        )
        done.append(c["ticker"])
    return {"set": done, "skipped": skipped}


def portfolio_view(conn: sqlite3.Connection) -> dict:
    """Positions with value, drifted weight and latest-day impact, plus portfolio totals."""
    rows = conn.execute(
        """SELECT c.ticker, c.name, c.sector, c.size, c.weight AS target_weight,
                  h.qty, h.start_price, h.start_date
           FROM companies c JOIN holdings h ON h.ticker = c.ticker
           WHERE c.in_portfolio = 1 ORDER BY c.weight DESC, c.ticker"""
    ).fetchall()
    positions, total_value, total_impact, total_prev = [], 0.0, 0.0, 0.0
    for r in rows:
        last2 = conn.execute(
            "SELECT date, close FROM prices WHERE ticker=? AND close IS NOT NULL ORDER BY date DESC LIMIT 2",
            (r["ticker"],),
        ).fetchall()
        if not last2:
            continue
        p_now = last2[0]["close"]
        p_prev = last2[1]["close"] if len(last2) > 1 else p_now
        value = r["qty"] * p_now
        impact = r["qty"] * (p_now - p_prev)
        positions.append({
            "ticker": r["ticker"], "name": r["name"], "sector": r["sector"], "size": r["size"],
            "target_weight": r["target_weight"], "qty": r["qty"], "price": p_now, "prev_price": p_prev,
            "as_of": last2[0]["date"], "value": value, "day_impact": impact,
            "day_change_pct": (p_now / p_prev - 1) * 100 if p_prev else None,
            "start_price": r["start_price"], "since_start_pct": (p_now / r["start_price"] - 1) * 100,
        })
        total_value += value
        total_impact += impact
        total_prev += r["qty"] * p_prev
    for p in positions:
        p["weight"] = p["value"] / total_value * 100 if total_value else 0.0
    return {
        "positions": positions,
        "total_value": total_value,
        "day_impact": total_impact,
        "day_impact_pct": total_impact / total_prev * 100 if total_prev else 0.0,
    }
