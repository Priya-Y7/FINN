"""P-10..P-16: alert rules, one engine for real runs and backtest previews, and the inbox."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from .. import config, db
from ..joblog import job
from ..metrics import add_metrics

DEFAULT_RULES = [
    ("price", {"mode": "z", "z": 2.5, "pct": 4.0, "overrides": {}}),
    ("volume", {"n": 20, "ratio": 2.0}),
    ("announcement", {"categories": ["results", "management_change", "m&a", "litigation"], "min_tier": 1, "keyword": ""}),
    ("confirmed", {}),
]
LOOKBACK_DAYS = 7


def seed_default_rules(conn) -> None:
    if conn.execute("SELECT COUNT(*) c FROM alert_rules").fetchone()["c"]:
        return
    cfg = config.settings()["metrics"]
    for typ, params in DEFAULT_RULES:
        if typ == "price":
            params = {**params, "z": cfg["z_threshold"], "pct": cfg["fixed_pct_threshold"]}
        if typ == "volume":
            params = {**params, "n": cfg["window_days"], "ratio": cfg["volume_ratio_threshold"]}
        conn.execute("INSERT INTO alert_rules(type, tickers_json, params_json, active, created_at) VALUES (?,?,?,?,?)",
                     (typ, None, db.dumps(params), 1, db.now_iso()))


def _frame(conn, ticker: str, window: int) -> pd.DataFrame:
    rows = conn.execute("SELECT date, close, volume FROM prices WHERE ticker=? AND close IS NOT NULL ORDER BY date", (ticker,)).fetchall()
    if not rows:
        return pd.DataFrame()
    return add_metrics(pd.DataFrame([dict(r) for r in rows]), window)


def price_fires(params: dict, ticker: str, df: pd.DataFrame, min_date: str) -> list[tuple[str, dict]]:
    o = (params.get("overrides") or {}).get(ticker, {})
    mode, z, pct = o.get("mode", params.get("mode", "z")), o.get("z", params.get("z", 2.5)), o.get("pct", params.get("pct", 4.0))
    out = []
    for r in df[df["date"] >= min_date].itertuples():
        if r.ret_pct is None or pd.isna(r.ret_pct):
            continue
        if mode == "z":
            if pd.notna(r.z_ret) and abs(r.z_ret) >= z:
                out.append((r.date, {"text": f"Price {r.ret_pct:+.1f}% (z {r.z_ret:+.1f}, unusual for this stock)", "ret_pct": r.ret_pct, "z": r.z_ret}))
        elif abs(r.ret_pct) >= pct:
            out.append((r.date, {"text": f"Price {r.ret_pct:+.1f}% (beyond ±{pct:g}%)", "ret_pct": r.ret_pct}))
    return out


def volume_fires(params: dict, ticker: str, df: pd.DataFrame, min_date: str) -> list[tuple[str, dict]]:
    ratio, floor = params.get("ratio", 2.0), config.settings()["metrics"]["min_avg_volume"]
    out = []
    for r in df[df["date"] >= min_date].itertuples():
        if pd.isna(r.vol_ratio) or r.vol_ratio < ratio:
            continue
        avg = r.volume / r.vol_ratio if r.vol_ratio else 0
        if avg < floor:
            continue
        out.append((r.date, {"text": f"Volume {r.vol_ratio:.1f}x average", "vol_ratio": r.vol_ratio, "ret_pct": None if pd.isna(r.ret_pct) else r.ret_pct}))
    return out


def _scope(conn, rule_tickers) -> list[str]:
    if rule_tickers:
        return rule_tickers
    return [r["ticker"] for r in conn.execute("SELECT ticker FROM companies WHERE in_portfolio=1")]


def preview(conn, typ: str, params: dict, tickers: list[str] | None = None, days: int = 30) -> dict:
    """P-16: replay stored prices with the same functions the engine uses."""
    min_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    window = params.get("n", config.settings()["metrics"]["window_days"]) if typ == "volume" else config.settings()["metrics"]["window_days"]
    fires = []
    for t in _scope(conn, tickers):
        df = _frame(conn, t, window)
        if df.empty:
            continue
        fn = price_fires if typ == "price" else volume_fires
        fires += [{"ticker": t, "date": d, **det} for d, det in fn(params, t, df, min_date)]
    by_day: dict[str, int] = {}
    for f in fires:
        by_day[f["date"]] = by_day.get(f["date"], 0) + 1
    return {"count": len(fires), "days": days, "by_day": by_day, "sample": fires[:10]}


def _insert(conn, rule_id, ticker, date, kind, detail) -> bool:
    cur = conn.execute("INSERT OR IGNORE INTO alerts_fired(rule_id,ticker,date,kind,detail_json,status,created_at) VALUES (?,?,?,?,?,'new',?)",
                       (rule_id, ticker, date, kind, db.dumps(detail), db.now_iso()))
    return cur.rowcount > 0


def evaluate() -> dict:
    """P-14: one alert per (rule, ticker, date, kind); safe to re-run."""
    created = 0
    min_date = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    with job("evaluate_alerts") as j, db.session() as conn:
        seed_default_rules(conn)
        rules = [dict(r) for r in conn.execute("SELECT * FROM alert_rules WHERE active=1")]
        by_type = {r["type"]: r for r in rules}
        fired: dict[tuple, dict] = {}
        for rule in rules:
            params = json.loads(rule["params_json"] or "{}")
            tickers = json.loads(rule["tickers_json"]) if rule["tickers_json"] else None
            if rule["type"] in ("price", "volume"):
                window = params.get("n", 20) if rule["type"] == "volume" else config.settings()["metrics"]["window_days"]
                for t in _scope(conn, tickers):
                    df = _frame(conn, t, window)
                    if df.empty:
                        continue
                    fn = price_fires if rule["type"] == "price" else volume_fires
                    for d, det in fn(params, t, df, min_date):
                        created += _insert(conn, rule["id"], t, d, rule["type"], det)
                        fired[(rule["type"], t, d)] = det
            elif rule["type"] == "announcement":
                cats, min_tier, kw = set(params.get("categories", [])), params.get("min_tier", 2), (params.get("keyword") or "").lower()
                scope = set(_scope(conn, tickers))
                for a in conn.execute("SELECT id,ticker,ts,title,category,tier FROM announcements WHERE ts>=? AND tier IS NOT NULL", (min_date,)):
                    if a["ticker"] not in scope or (cats and a["category"] not in cats) or a["tier"] > min_tier:
                        continue
                    if kw and kw not in a["title"].lower():
                        continue
                    created += _insert(conn, rule["id"], a["ticker"], a["ts"][:10], f"announcement:{a['id']}",
                                       {"text": f"{(a['category'] or '').replace('_', ' ').title()}: {a['title']}", "announcement_id": a["id"]})
        if "confirmed" in by_type:   # P-13
            for (typ, t, d), det in list(fired.items()):
                if typ == "price" and ("volume", t, d) in fired:
                    v = fired[("volume", t, d)]
                    created += _insert(conn, by_type["confirmed"]["id"], t, d, "confirmed",
                                       {"text": f"Confirmed move: price {det['ret_pct']:+.1f}% on {v['vol_ratio']:.1f}x volume"})
        j.rows = created
    return {"created": created}


def inbox(conn, status: str | None = None, limit: int = 100) -> list[dict]:
    q = """SELECT a.id, a.ticker, a.date, a.kind, a.detail_json, a.status, a.created_at, c.name,
                  (SELECT ret_pct FROM prices p WHERE p.ticker=a.ticker AND p.date<=a.date ORDER BY p.date DESC LIMIT 1) AS day_change
           FROM alerts_fired a JOIN companies c ON c.ticker=a.ticker WHERE a.status != 'dismissed'"""
    args: list = []
    if status:
        q += " AND a.status=?"
        args.append(status)
    q += " ORDER BY a.date DESC, a.id DESC LIMIT ?"
    args.append(limit)
    out = []
    for r in conn.execute(q, args):
        d = dict(r)
        d["detail"] = json.loads(d.pop("detail_json") or "{}")
        d["kind_label"] = d["kind"].split(":")[0]
        out.append(d)
    return out
