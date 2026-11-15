"""R-16..R-19: the financial snapshot. Pure code, no model."""
from __future__ import annotations

import math

import pandas as pd

from .periods import year_label

DEFAULTS = {"grow_cagr_pct": 8.0, "compress_bps": 100.0, "cash_conv_min": 0.7}


def cagr(end, start, n: int):
    """CAGR = (X_end / X_start)^(1/n) - 1, in %. None when undefined."""
    if end is None or start is None or n <= 0 or start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1 / n) - 1) * 100


def _lbl(idx: str) -> str:
    y, m = idx.split("-")
    return year_label(int(y), int(m))


def _series(df: pd.DataFrame, col: str, n: int = 5) -> list[float | None]:
    if col not in df:
        return []
    return [None if pd.isna(v) else float(v) for v in df[col].tail(n)]


def build(df: pd.DataFrame, q: pd.DataFrame | None = None, th: dict | None = None) -> dict:
    th = {**DEFAULTS, **(th or {})}
    if df.empty:
        return {"available": False}
    d = df.copy()
    d["op_margin"] = d["operating_profit"] / d["sales"] * 100
    if "borrowings" in d and "equity" in d:
        d["de"] = d["borrowings"] / d["equity"]
    if "cfo" in d:
        d["cash_conv"] = d["cfo"] / d["pat"].where(d["pat"] > 0)
    if "cfo" in d and "capex" in d:
        d["fcf"] = d["cfo"] - d["capex"].abs()
    last = d.iloc[-1]
    ltm_sales = None
    if q is not None and not q.empty and "sales" in q and len(q) >= 4:
        ltm_sales = float(q["sales"].tail(4).sum())
    g = lambda c: None if c not in d or pd.isna(last[c]) else float(last[c])

    tiles = [
        {"key": "revenue", "label": "Revenue (LTM)" if ltm_sales else "Revenue", "value": ltm_sales or g("sales"), "unit": "crore",
         "spark": _series(d, "sales"), "formula": "Sum of the last four quarters' sales" if ltm_sales else "Latest annual sales"},
        {"key": "op_margin", "label": "Operating margin", "value": g("op_margin"), "unit": "%", "spark": _series(d, "op_margin"),
         "formula": "Operating profit / Sales x 100 (screener's operating profit; a close stand-in for EBITDA margin)"},
        {"key": "pat", "label": "PAT", "value": g("pat"), "unit": "crore", "spark": _series(d, "pat"), "formula": "Net profit after tax"},
        {"key": "roce", "label": "ROCE", "value": g("roce_pct"), "unit": "%", "spark": _series(d, "roce_pct"), "formula": "As reported by screener.in"},
        {"key": "de", "label": "Debt to equity", "value": g("de"), "unit": "x", "spark": _series(d, "de"),
         "formula": "Borrowings / (Equity capital + Reserves)"},
        {"key": "cash_conv", "label": "Cash conversion", "value": g("cash_conv"), "unit": "x", "spark": _series(d, "cash_conv"),
         "formula": "Cash from operations / PAT"},
    ]
    years = [_lbl(i) for i in d.index][-10:]
    traj = {"years": years, "revenue": _series(d, "sales", 10), "pat": _series(d, "pat", 10), "margin": _series(d, "op_margin", 10)}

    callouts = []
    n3 = min(3, len(d) - 1)
    if n3 >= 1:
        c3 = cagr(d["sales"].iloc[-1], d["sales"].iloc[-1 - n3], n3)
        m_chg = (d["op_margin"].iloc[-1] - d["op_margin"].iloc[-1 - n3]) * 100
        if c3 is not None and c3 > th["grow_cagr_pct"]:
            callouts.append({"kind": "growing", "text": f"Revenue +{c3:.0f}% a year over {n3} years"
                             + (f"; margin {'down' if m_chg < 0 else 'up'} {abs(m_chg):.0f} bps since {_lbl(d.index[-1 - n3])}." if not math.isnan(m_chg) and abs(m_chg) >= 10 else ".")})
        if m_chg < -th["compress_bps"]:
            callouts.append({"kind": "compressing", "text": f"Operating margin down {abs(m_chg):.0f} bps over {n3} years."})
    if "cash_conv" in d and len(d) >= 2 and all((not pd.isna(x)) and x < th["cash_conv_min"] for x in d["cash_conv"].tail(2)):
        callouts.append({"kind": "cash", "text": f"Cash conversion under {th['cash_conv_min']:.1f}x for two years running: profit is not turning into cash."})

    health = {"working_capital_days": [{"year": _lbl(i), "days": None if pd.isna(r) else float(r)} for i, r in
                                       ((d.index[k], (d.get("debtor_days", pd.Series(dtype=float)).iloc[k] if "debtor_days" in d else float("nan"))
                                         + (d["inventory_days"].iloc[k] if "inventory_days" in d else 0)
                                         - (d["payable_days"].iloc[k] if "payable_days" in d else 0)) for k in range(len(d)))][-5:],
              "fcf": [{"year": _lbl(i), "value": None if pd.isna(v) else float(v)} for i, v in d["fcf"].tail(5).items()] if "fcf" in d else []}
    return {"available": True, "as_of": _lbl(d.index[-1]), "tiles": tiles, "trajectory": traj, "callouts": callouts, "health": health,
            "thresholds": th}
