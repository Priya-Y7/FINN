"""Classify -> de-duplicate -> score -> enrich. Idempotent: re-running changes nothing already done."""
from __future__ import annotations

import json
import re

from .. import config, db
from ..joblog import job
from . import enrich as enrich_mod
from .classify import classify
from .score import score

ENRICH_CATEGORIES = {"results", "management_change", "dividend", "bonus_split", "fund_raise", "m&a", "litigation",
                     "credit_rating", "pledging", "insider_trading", "capex", "press_release", "earnings_call"}
ROUTINE = {"investor_meetings", "postal_ballot", "agm_egm", "unclassified"}   # P-29: no model


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (t or "").lower()).strip()


def dedupe(conn) -> int:
    """P-08: same (ticker, normalised title, date) on NSE and BSE becomes one row; both links kept."""
    rows = conn.execute("SELECT id, ticker, ts, title, source, pdf_url, enrichment_json FROM announcements ORDER BY ts, id").fetchall()
    seen, removed = {}, 0
    for r in rows:
        key = (r["ticker"], norm_title(r["title"]), r["ts"][:10])
        if key not in seen:
            seen[key] = r["id"]
            continue
        keep = seen[key]
        if r["pdf_url"]:
            e = json.loads(conn.execute("SELECT enrichment_json FROM announcements WHERE id=?", (keep,)).fetchone()[0] or "{}")
            e.setdefault("alt_links", []).append({"source": r["source"], "url": r["pdf_url"]})
            conn.execute("UPDATE announcements SET enrichment_json=? WHERE id=?", (db.dumps(e), keep))
        conn.execute("DELETE FROM announcements WHERE id=?", (r["id"],))
        removed += 1
    return removed


def _reaction(conn, ticker: str, ts: str) -> list[tuple]:
    """Return/volume ratio on the filing day and the next trading day (P-06 M_mkt)."""
    day = ts[:10]
    rows = conn.execute("SELECT ret_pct, vol_ratio FROM prices WHERE ticker=? AND date>=? ORDER BY date LIMIT 2",
                        (ticker, day)).fetchall()
    return [(r["ret_pct"], r["vol_ratio"]) for r in rows]


def run(enrich: bool = True, use_llm: bool = True) -> dict:
    stats = {"classified": 0, "deduped": 0, "scored": 0, "enriched": 0}
    with job("process_announcements") as j:
        # Model calls open their own connections, so no connection is held open across them.
        with db.session() as conn:
            stats["deduped"] = dedupe(conn)
            companies = {r["ticker"]: dict(r) for r in conn.execute("SELECT * FROM companies")}
            max_w = max((c["weight"] for c in companies.values()), default=0)
            anns = [dict(r) for r in conn.execute("SELECT * FROM announcements")]
        for a in anns:
            cat = a["category"]
            if cat is None:
                cat, _ = classify(a["ticker"], a["category_text"], a["title"], use_llm=use_llm)
                stats["classified"] += 1
            comp = companies.get(a["ticker"], {})
            with db.session() as conn:
                react = _reaction(conn, a["ticker"], a["ts"])
                last = conn.execute("SELECT close FROM prices WHERE ticker=? ORDER BY date DESC LIMIT 1", (a["ticker"],)).fetchone()
            s = score(cat, f"{a['category_text'] or ''} {a['title']}", react,
                      comp.get("weight") if comp.get("in_portfolio") else None, max_w)
            enr = json.loads(a["enrichment_json"] or "{}")
            enr["breakdown"] = s["breakdown"]
            summary = a["summary"]
            if enrich and cat in ENRICH_CATEGORIES and "card" not in enr and s["tier"] <= 2:
                a["category"] = cat
                if cat == "results":
                    card = enrich_mod.enrich_results(a, bool(comp.get("is_bank")))
                else:
                    card = enrich_mod.enrich_other(a, last["close"] if last else None)
                if card and not (card.get("needs_review") and "no API key" in " ".join(card.get("problems", []))):
                    enr["card"] = card
                    summary = card.get("sentence") or card.get("line") or summary
                    stats["enriched"] += 1
            with db.session() as conn:
                conn.execute("UPDATE announcements SET category=?, score=?, tier=?, enrichment_json=?, summary=? WHERE id=?",
                             (cat, s["score"], s["tier"], db.dumps(enr), summary, a["id"]))
            stats["scored"] += 1
        j.rows = stats["scored"]
        j.note(json.dumps(stats))
    return stats
