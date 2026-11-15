"""FINN API. Reads the SQLite store; refresh runs in the background."""
from __future__ import annotations

import threading

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .. import config, db, holdings
from ..pipeline import refresh as refresh_pipeline
from ..push import alerts as alerts_mod, digest as digest_mod
import json
from fastapi import Header
from fastapi.responses import StreamingResponse
from ..pull import ask as ask_mod, research as research_mod, runner
from ..pull.retrieval import load_chunks, source_label
from ..cache import cache_get, cache_key

app = FastAPI(title="FINN API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_refresh_lock = threading.Lock()


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    # Fresh host (e.g. Render): the working DB is not committed, so seed it from the frozen snapshot.
    with db.session() as conn:
        empty = conn.execute("SELECT COUNT(*) c FROM prices").fetchone()["c"] == 0
    if empty:
        from .. import snapshot_store
        if snapshot_store.load():
            db.init_db()
    with db.session() as conn:
        alerts_mod.seed_default_rules(conn)
    if config.env_flag("FINN_AUTO_REFRESH"):
        from .. import scheduler
        scheduler.start()


def rows(conn, sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/meta")
def meta():
    with db.session() as conn:
        last_job = rows(conn, "SELECT name, status, started_at, finished_at, rows, error FROM job_runs ORDER BY id DESC LIMIT 1")
        has_prices = conn.execute("SELECT COUNT(*) c FROM prices").fetchone()["c"] > 0
        return {
            "data_mode": db.get_meta(conn, "data_mode", "empty") if has_prices else "empty",
            "prices_refreshed_at": db.get_meta(conn, "prices_refreshed_at"),
            "announcements_refreshed_at": db.get_meta(conn, "announcements_refreshed_at"),
            "last_job": last_job[0] if last_job else None,
            "llm_mock": __import__("backend.llm", fromlist=["is_mock"]).is_mock(),
        }


@app.get("/companies")
def companies(portfolio_only: bool = False):
    with db.session() as conn:
        where = "WHERE in_portfolio=1" if portfolio_only else ""
        return rows(conn, f"SELECT ticker,name,sector,size,is_bank,in_portfolio,weight FROM companies {where} ORDER BY in_portfolio DESC, weight DESC, ticker")


class AddIn(BaseModel):
    ticker: str


@app.post("/companies/add")
def add_company(body: AddIn):
    """Make any NSE ticker researchable: checks it exists on Yahoo, stores its prices, then Ask can use it."""
    from ..pipeline import add_company as ac
    from ..sources import SourceError
    try:
        return ac.add(body.ticker)
    except SourceError as exc:
        raise HTTPException(404, str(exc))


@app.get("/companies/search")
def search(q: str = Query(min_length=1)):
    like = f"%{q}%"
    with db.session() as conn:
        return rows(conn, "SELECT ticker,name,sector,in_portfolio FROM companies WHERE ticker LIKE ? OR name LIKE ? ORDER BY in_portfolio DESC LIMIT 10", (like, like))


@app.get("/portfolio")
def portfolio():
    with db.session() as conn:
        return holdings.portfolio_view(conn)


@app.get("/stocks/{ticker}/prices")
def prices(ticker: str, days: int = 90):
    with db.session() as conn:
        data = rows(conn, "SELECT date,open,high,low,close,volume,ret_pct,vol_ratio,z_ret FROM prices WHERE ticker=? ORDER BY date DESC LIMIT ?", (ticker.upper(), days))
    if not data:
        raise HTTPException(404, f"no prices for {ticker}")
    return list(reversed(data))


@app.get("/announcements")
def announcements(ticker: str | None = None, days: int = 7, limit: int = 100):
    with db.session() as conn:
        sql = "SELECT id,ticker,ts,source,title,category_text,category,pdf_url,tier,score,summary,is_sample FROM announcements WHERE ts >= datetime('now', ?)"
        args: list = [f"-{days} days"]
        if ticker:
            sql += " AND ticker=?"
            args.append(ticker.upper())
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        return rows(conn, sql, tuple(args))


@app.post("/refresh")
def refresh(background: BackgroundTasks):
    if not _refresh_lock.acquire(blocking=False):
        return {"started": False, "reason": "refresh already running"}

    def work():
        try:
            refresh_pipeline.run()
        finally:
            _refresh_lock.release()

    background.add_task(work)
    return {"started": True}


@app.get("/jobs")
def jobs(limit: int = 20):
    with db.session() as conn:
        return rows(conn, "SELECT * FROM job_runs ORDER BY id DESC LIMIT ?", (limit,))


@app.get("/digest")
def digest(frm: str | None = Query(None, alias="from"), to: str | None = None, days: int = 1, all_stocks: bool = False):
    with db.session() as conn:
        return digest_mod.build(conn, frm, to, days, only_portfolio=not all_stocks)


@app.get("/announcements/{ann_id}")
def announcement(ann_id: str):
    with db.session() as conn:
        r = conn.execute("SELECT * FROM announcements WHERE id=?", (ann_id,)).fetchone()
        if not r:
            raise HTTPException(404, "not found")
        d = dict(r)
        enr = json.loads(d.pop("enrichment_json") or "{}")
        d.update(card=enr.get("card"), breakdown=enr.get("breakdown"), alt_links=enr.get("alt_links", []))
        return d


@app.get("/alerts")
def alerts(status: str | None = None):
    with db.session() as conn:
        items = alerts_mod.inbox(conn, status)
        unread = conn.execute("SELECT COUNT(*) c FROM alerts_fired WHERE status='new'").fetchone()["c"]
        return {"unread": unread, "items": items}


@app.post("/alerts/{alert_id}/dismiss")
def dismiss(alert_id: int):
    with db.session() as conn:
        conn.execute("UPDATE alerts_fired SET status='dismissed' WHERE id=?", (alert_id,))
    return {"ok": True}


@app.post("/alerts/{alert_id}/seen")
def seen(alert_id: int):
    with db.session() as conn:
        conn.execute("UPDATE alerts_fired SET status='seen' WHERE id=? AND status='new'", (alert_id,))
    return {"ok": True}


class RuleIn(BaseModel):
    type: str
    params: dict = {}
    tickers: list[str] | None = None
    active: bool = True


class PreviewIn(BaseModel):
    type: str
    params: dict = {}
    tickers: list[str] | None = None
    days: int = 30


def _rule(r) -> dict:
    d = dict(r)
    return {"id": d["id"], "type": d["type"], "params": json.loads(d["params_json"] or "{}"),
            "tickers": json.loads(d["tickers_json"]) if d["tickers_json"] else None, "active": bool(d["active"])}


@app.get("/alert-rules")
def list_rules():
    with db.session() as conn:
        return [_rule(r) for r in conn.execute("SELECT * FROM alert_rules ORDER BY id")]


@app.post("/alert-rules")
def create_rule(body: RuleIn):
    if body.type not in ("price", "volume", "announcement", "confirmed"):
        raise HTTPException(400, "unknown rule type")
    with db.session() as conn:
        cur = conn.execute("INSERT INTO alert_rules(type,tickers_json,params_json,active,created_at) VALUES (?,?,?,?,?)",
                           (body.type, json.dumps(body.tickers) if body.tickers else None, db.dumps(body.params), int(body.active), db.now_iso()))
        return _rule(conn.execute("SELECT * FROM alert_rules WHERE id=?", (cur.lastrowid,)).fetchone())


@app.put("/alert-rules/{rule_id}")
def update_rule(rule_id: int, body: RuleIn):
    with db.session() as conn:
        conn.execute("UPDATE alert_rules SET params_json=?, tickers_json=?, active=? WHERE id=?",
                     (db.dumps(body.params), json.dumps(body.tickers) if body.tickers else None, int(body.active), rule_id))
        r = conn.execute("SELECT * FROM alert_rules WHERE id=?", (rule_id,)).fetchone()
        if not r:
            raise HTTPException(404, "no such rule")
    alerts_mod.evaluate()
    return _rule(r)


@app.post("/alert-rules/preview")
def preview_rule(body: PreviewIn):
    if body.type not in ("price", "volume"):
        raise HTTPException(400, "preview supports price and volume rules")
    with db.session() as conn:
        return alerts_mod.preview(conn, body.type, body.params, body.tickers, body.days)


# ---------- Pull ----------
_ask_counts: dict[tuple, int] = {}


@app.get("/research/recent")
def research_recent():
    with db.session() as conn:
        return rows(conn, """SELECT j.ticker, c.name, MAX(j.updated_at) at FROM research_jobs j JOIN companies c ON c.ticker=j.ticker
                             WHERE j.status='done' GROUP BY j.ticker ORDER BY at DESC LIMIT 6""")


@app.get("/research/{ticker}/stream")
def research_stream(ticker: str):
    with db.session() as conn:
        if not conn.execute("SELECT 1 FROM companies WHERE ticker=?", (ticker.upper(),)).fetchone():
            raise HTTPException(404, "unknown company")
    return StreamingResponse(runner.stream(ticker), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/research/{ticker}")
def research_start(ticker: str):
    run = runner.start(ticker)
    return {"started": True, "running": not run["done"]}


@app.get("/research/{ticker}")
def research_get(ticker: str):
    """Latest cached result, if the documents are unchanged since it was built."""
    from datetime import date
    t = ticker.upper()
    with db.session() as conn:
        key = cache_key("research", t, research_mod.doc_hash(conn, t), str(date.today()), "v2")
        hit = cache_get(conn, key)
    return {"status": "ready", **hit} if hit else {"status": "none"}


@app.get("/sources/{ticker}/{chunk_id}")
def source(ticker: str, chunk_id: str):
    with db.session() as conn:
        for c in load_chunks(conn, ticker.upper()):
            if c["id"] == chunk_id:
                return {"id": chunk_id, "label": source_label(c), "document": c["title"], "page": c["page"], "section": c["section"],
                        "text": c["text"], "url": None if (c["url"] or "").startswith("sample://") else c["url"], "sample": (c["url"] or "").startswith("sample://")}
    raise HTTPException(404, "source not found")


class AskIn(BaseModel):
    question: str
    filing_id: str | None = None


@app.post("/research/{ticker}/ask")
def research_ask(ticker: str, body: AskIn, x_session: str = Header("anon")):
    t = ticker.upper()
    k = (x_session, t)
    if _ask_counts.get(k, 0) >= ask_mod.CAP:
        raise HTTPException(429, f"Limit of {ask_mod.CAP} questions per company reached for this session.")
    with db.session() as conn:
        chunks = load_chunks(conn, t)
        if body.filing_id:
            f = conn.execute("SELECT title, summary, ts FROM announcements WHERE id=?", (body.filing_id,)).fetchone()
            if f:
                chunks.append({"id": "F-" + body.filing_id[:8], "page": 1, "section": "Filing", "doc_type": "filing", "period": f["ts"][:10],
                               "title": "Exchange filing", "url": "", "text": f"{f['title']}. {f['summary'] or ''}"})
        h = research_mod.doc_hash(conn, t)
    _ask_counts[k] = _ask_counts.get(k, 0) + 1
    res = ask_mod.answer(t, body.question, chunks, h + (body.filing_id or ""))
    return {**res, "remaining": ask_mod.CAP - _ask_counts[k]}


@app.get("/usage")
def usage():
    """P-34: model calls and tokens by class, for the cost note in the write-up."""
    from .. import llm
    return llm.usage_summary()


@app.get("/portfolio/history")
def portfolio_history(days: int = 90):
    """Portfolio value per day = sum(qty x close) over holdings."""
    with db.session() as conn:
        data = rows(conn, """SELECT p.date, SUM(h.qty * p.close) AS value FROM prices p JOIN holdings h ON h.ticker=p.ticker
                             JOIN companies c ON c.ticker=p.ticker WHERE c.in_portfolio=1 AND p.close IS NOT NULL
                             GROUP BY p.date ORDER BY p.date DESC LIMIT ?""", (days,))
    return list(reversed(data))


@app.get("/overview")
def overview(spark_days: int = 30):
    """Every company with last price, day change and a small price series (for tiles and the Ask landing page)."""
    with db.session() as conn:
        out = []
        for c in conn.execute("SELECT ticker,name,sector,size,in_portfolio,weight FROM companies ORDER BY in_portfolio DESC, weight DESC, ticker"):
            px = conn.execute("SELECT close, ret_pct FROM prices WHERE ticker=? AND close IS NOT NULL ORDER BY date DESC LIMIT ?", (c["ticker"], spark_days)).fetchall()
            if not px:
                continue
            out.append({**dict(c), "price": px[0]["close"], "day_change": px[0]["ret_pct"], "spark": [r["close"] for r in reversed(px)]})
        return out
