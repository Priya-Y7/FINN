"""R-26/R-27/R-28: orchestrate a research run. Each section fails alone; results cached by document hash."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Callable

from .. import config, db
from ..cache import cache_get, cache_key, cache_set
from . import bullbear, docs, financials, promises as P, snapshot
from .retrieval import Index, load_chunks, source_label

Emit = Callable[[str, dict], None]


def doc_hash(conn, ticker: str) -> str:
    rows = conn.execute("SELECT id, COALESCE(sha256,url) h FROM documents WHERE ticker=? AND id IN (SELECT DISTINCT document_id FROM chunks) ORDER BY id", (ticker,)).fetchall()
    fin = conn.execute("SELECT COUNT(*), COALESCE(SUM(value),0) FROM financials WHERE ticker=?", (ticker,)).fetchone()
    return hashlib.sha256(json.dumps([[r[0], r[1]] for r in rows] + [list(fin)]).encode()).hexdigest()[:16]


def _calls(chunks: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for c in chunks:
        if c["doc_type"] == "transcript":
            out.setdefault(c["period"], []).append(c)
    return out


def ensure_inputs(ticker: str, emit: Emit) -> list[str]:
    """Try live fetches only for what is missing. Returns notes about what could not be fetched."""
    notes = []
    with db.session() as conn:
        has_fin = conn.execute("SELECT COUNT(*) FROM financials WHERE ticker=?", (ticker,)).fetchone()[0] > 0
        has_chunks = conn.execute("SELECT COUNT(*) FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.ticker=?", (ticker,)).fetchone()[0] > 0
    from ..sources import SourceError
    if not has_fin:
        emit("step", {"text": "Fetching financial tables..."})
        try:
            financials.fetch_and_store(ticker)
        except SourceError as exc:
            notes.append(f"financials unavailable: {exc}")
    if not has_chunks:
        emit("step", {"text": "Reading annual report and transcripts..."})
        try:
            from ..pipeline import fetch_documents
            fetch_documents.run([ticker])
            docs.ingest(ticker)
        except SourceError as exc:
            notes.append(f"documents unavailable: {exc}")
    return notes


def run(ticker: str, emit: Emit | None = None, today: date | None = None) -> dict:
    emit = emit or (lambda *_: None)
    ticker = ticker.upper()
    with db.session() as conn:
        name = conn.execute("SELECT name FROM companies WHERE ticker=?", (ticker,)).fetchone()
        job_id = conn.execute("INSERT INTO research_jobs(ticker,status,step,created_at,updated_at) VALUES (?,?,?,?,?)",
                              (ticker, "running", "start", db.now_iso(), db.now_iso())).lastrowid
    if not name:
        raise KeyError(ticker)
    notes = ensure_inputs(ticker, emit)
    with db.session() as conn:
        h = doc_hash(conn, ticker)
        key = cache_key("research", ticker, h, str(today or date.today()), "v2")
        hit = cache_get(conn, key)
        if hit:
            conn.execute("UPDATE research_jobs SET status='done', step='cached', updated_at=? WHERE id=?", (db.now_iso(), job_id))
            for s in ("snapshot", "promises", "bull_bear"):
                emit("section", {"name": s, "data": hit[s]})
            return {**hit, "cached": True}
        annual, quarterly = financials.load(conn, ticker, "A"), financials.load(conn, ticker, "Q")
        chunks = load_chunks(conn, ticker)
        is_sample = bool(conn.execute("SELECT 1 FROM financials WHERE ticker=? AND is_sample=1 LIMIT 1", (ticker,)).fetchone())
    result: dict = {"ticker": ticker, "name": name["name"], "as_of": str(today or date.today()), "doc_hash": h, "notes": notes,
                    "sample": is_sample, "consolidated_note": "Figures in rupees crore. Consolidated where available."}

    def step(text, status="running"):
        emit("step", {"text": text})
        with db.session() as conn:
            conn.execute("UPDATE research_jobs SET step=?, updated_at=? WHERE id=?", (text, db.now_iso(), job_id))

    # 1. snapshot (no model)
    try:
        step("Building financial snapshot...")
        result["snapshot"] = snapshot.build(annual, quarterly) if not annual.empty else {"available": False, "reason": "No financial tables found. Check the filings on the exchange sites."}
    except Exception as exc:  # noqa: BLE001
        result["snapshot"] = {"available": False, "reason": f"Snapshot failed: {exc}"}
    emit("section", {"name": "snapshot", "data": result["snapshot"]})

    # 2. promised vs delivered
    try:
        calls = _calls(chunks)
        if not calls:
            result["promises"] = {"available": False, "reason": "No earnings-call transcripts found for this company.", "calls": 0}
        else:
            step(f"Reading {len(calls)} transcripts...")
            raw = P.extract(calls)
            step("Checking promises...")
            idx = {c["id"]: c for c in chunks}
            kept, dropped = P.verify([P.normalise(p) for p in raw], idx)
            scored = [P.score(p, annual, quarterly, today) for p in kept]
            flg = P.flags(kept, calls, quarterly)
            dr = P.delivery_rate(scored)
            step("Writing verdict...")
            v = P.verdict(scored, flg, dr)
            for s in scored:
                s["horizon_label"] = P.horizon_label(s.get("horizon"))
                s["source_label"] = source_label(idx[s["source_id"]])
                s["metric_name"] = P.METRIC_NAME.get(s["metric"], s["metric"])
                s["unit"] = P.METRICS.get(s["metric"], ("", "", False))[1]
            result["promises"] = {"available": True, "promises": scored, "flags": flg, "delivery": dr, "verdict": v, "calls": len(calls),
                                  "calls_note": f"Only {len(calls)} of 4 calls available" if len(calls) < 4 else None,
                                  "dropped_unverified": dropped, "chips": chips(scored, flg)}
    except Exception as exc:  # noqa: BLE001
        result["promises"] = {"available": False, "reason": f"Promise check failed: {exc}"}
    emit("section", {"name": "promises", "data": result["promises"]})

    # 3. bull vs bear
    try:
        if not chunks:
            result["bull_bear"] = {"available": False, "reason": "No company documents to build a case from."}
        else:
            step("Writing bull and bear cases...")
            sc = result["promises"] if result["promises"].get("available") else {"delivery": {}, "flags": [], "promises": []}
            bb = bullbear.generate(result["snapshot"], sc, Index(chunks))
            if bb.get("available"):
                idx = {c["id"]: c for c in chunks}
                bb["sources"] = {i: {"label": source_label(idx[i]) if i in idx else "Financial snapshot"} for p in bb["bull"] + bb["bear"] for i in p["ids"]}
            result["bull_bear"] = bb
    except Exception as exc:  # noqa: BLE001
        result["bull_bear"] = {"available": False, "reason": f"Bull/bear failed: {exc}"}
    emit("section", {"name": "bull_bear", "data": result["bull_bear"]})

    with db.session() as conn:
        if all(result[s].get("available") is not None for s in ("snapshot", "promises", "bull_bear")) and not notes:
            cache_set(conn, key, "research", result)
        conn.execute("UPDATE research_jobs SET status='done', step='done', updated_at=? WHERE id=?", (db.now_iso(), job_id))
    return {**result, "cached": False}


def chips(scored: list[dict], flg: list[dict]) -> list[str]:
    """R-24: suggested questions by rules."""
    out = []
    missed = next((p for p in scored if p["status"] == "missed"), None)
    if missed:
        out.append(f"Why did the {missed['metric_name'].lower()} target slip?")
    if any(f["kind"] == "narrative_vs_numbers" for f in flg):
        out.append("Why is management upbeat while margins and sales are falling?")
    drop = next((f for f in flg if f["kind"] in ("dropped", "softened")), None)
    if drop:
        out.append("Did management explain the change in guidance?")
    out += ["What are the main risks management highlights?", "What is the outlook for the next year?", "What is the capex plan?"]
    return out[:3]
