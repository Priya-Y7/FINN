"""P-17, P-22..P-28: turn a filing into a card. Cheap model only; arithmetic is done in code.

Real path: download PDF, find the statement pages, send only those to the cheap model, compute in code.
Sample/mock path: deterministic SYNTHETIC figures, flagged "synthetic": true so the UI can say so.
"""
from __future__ import annotations

import hashlib
import json
import re

import numpy as np

from .. import config, llm
from ..sources import SourceError
from ..sources.http import get
from . import calc

RESULTS_SYSTEM = (
    "Extract figures from an Indian company's quarterly results statement. Return JSON only: "
    '{"unit": "crore|lakh|million", "now": {...}, "qoq": {...}, "yoy": {...}} where now=current quarter, '
    "qoq=preceding quarter, yoy=same quarter last year, and each object has numeric keys: %s. "
    "Prefer the CONSOLIDATED statement. Use null for anything not shown. Do not calculate anything."
)

ONE_LINER_SYSTEM = {
    "management_change": 'Return JSON: {"name","role","action":"appointed|resigned|retired|other","effective_date","reason","successor","bio":"<=2 sentences if in text else null"}',
    "dividend": 'Return JSON: {"amount_per_share": number|null, "record_date": str|null}',
    "bonus_split": 'Return JSON: {"ratio": str|null, "record_date": str|null}',
    "fund_raise": 'Return JSON: {"type": str, "size_crore": number|null}',
    "m&a": 'Return JSON: {"target": str|null, "size_crore": number|null, "payment_form": str|null}',
    "litigation": 'Return JSON: {"authority": str|null, "nature": str|null, "amount_crore": number|null}',
    "credit_rating": 'Return JSON: {"agency": str|null, "instrument": str|null, "old": str|null, "new": str|null, "outlook": str|null}',
    "pledging": 'Return JSON: {"change_pct_of_promoter_holding": number|null}',
    "insider_trading": 'Return JSON: {"who": str|null, "side": "buy|sell", "quantity": number|null, "price": number|null}',
    "capex": 'Return JSON: {"amount_crore": number|null, "capacity": str|null, "timeline": str|null}',
    "press_release": 'Return JSON: {"fact": str}',
    "earnings_call": 'Return JSON: {"when": str|null}',
}


def statement_pages(pdf_bytes: bytes, max_pages: int = 4) -> str:
    """Only the pages that hold the statement go to the model (P-17)."""
    import pymupdf
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    hits = []
    for i, page in enumerate(doc):
        t = page.get_text()
        low = t.lower()
        if "revenue from operations" in low and "profit before" in low:
            hits.append((("consolidated" in low), i, t))
    hits.sort(key=lambda h: (not h[0], h[1]))   # consolidated first
    return "\n\n".join(t for _, _, t in hits[:max_pages])


def _synthetic_results(ticker: str, bank: bool) -> dict:
    rng = np.random.default_rng(int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16))
    base = float(rng.uniform(800, 9000))
    g_q, g_y = rng.uniform(-0.05, 0.12), rng.uniform(-0.1, 0.3)

    def col(rev):
        if bank:
            ie, ix = rev * 1.0, rev * 0.62
            nii = ie - ix
            opx, oi = nii * 0.38, nii * 0.15
            pbt = nii + oi - opx - nii * 0.15
            tax = pbt * 0.25
            return {"interest_earned": ie, "interest_expended": ix, "other_income": oi, "operating_expenses": opx,
                    "pbt": pbt, "tax": tax, "pat": pbt - tax}
        oi, fc, dep = rev * 0.02, rev * 0.03, rev * 0.05
        ebitda = rev * float(rng.uniform(0.14, 0.24))
        pbt = ebitda - fc - dep + oi
        tax = pbt * 0.25
        return {"revenue": rev, "other_income": oi, "finance_costs": fc, "depreciation": dep, "exceptional": 0,
                "pbt": pbt, "tax": tax, "pat": pbt - tax}

    r = lambda d: {k: round(v, 1) for k, v in d.items()}
    return {"unit": "crore", "now": r(col(base)), "qoq": r(col(base / (1 + g_q))), "yoy": r(col(base / (1 + g_y)))}


def enrich_results(ann: dict, bank: bool) -> dict:
    if ann["is_sample"]:
        card = calc.build_card(_synthetic_results(ann["ticker"], bank), bank)
        return {**card, "synthetic": True}
    if not ann["pdf_url"]:
        return {"kind": "results", "needs_review": True, "problems": ["no filing PDF link"]}
    try:
        pdf = get(ann["pdf_url"]).content
        text = statement_pages(pdf)
    except (SourceError, Exception) as exc:  # noqa: BLE001
        return {"kind": "results", "needs_review": True, "problems": [f"could not read PDF: {exc}"]}
    if not text:
        return {"kind": "results", "needs_review": True, "problems": ["statement pages not found in PDF"]}
    fields = calc.BANK_FIELDS if bank else calc.GENERAL_FIELDS
    r = llm.complete("extract_results", "cheap", RESULTS_SYSTEM % ", ".join(fields), text,
                     cache_parts=[hashlib.sha256(pdf).hexdigest(), bank], max_tokens=1500)
    if r["mock"]:
        return {"kind": "results", "needs_review": True, "problems": ["no API key: extraction skipped"]}
    try:
        return calc.build_card(llm.parse_json(r["text"]), bank)
    except Exception as exc:  # noqa: BLE001
        return {"kind": "results", "needs_review": True, "problems": [f"bad extraction: {exc}"]}


def _synthetic_other(category: str, title: str) -> dict:
    return {"management_change": {"name": "Sample Person", "role": "Chief Financial Officer", "action": "resigned",
                                  "successor": None, "effective_date": None, "bio": None},
            "dividend": {"amount_per_share": 5.0, "record_date": None},
            "credit_rating": {"agency": "CRISIL", "old": "AA", "new": "AA", "outlook": "Stable"}}.get(category, {})


def enrich_other(ann: dict, last_close: float | None) -> dict:
    cat = ann["category"]
    if cat not in ONE_LINER_SYSTEM:
        return {}
    if ann["is_sample"]:
        data = _synthetic_other(cat, ann["title"])
        synthetic = True
    else:
        r = llm.complete(f"extract_{cat}", "cheap", ONE_LINER_SYSTEM[cat], f"{ann['ticker']}\n{ann['title']}",
                         cache_parts=[ann["id"]], max_tokens=400, mock_response="{}")
        try:
            data = llm.parse_json(r["text"]) or {}
        except Exception:  # noqa: BLE001
            data = {}
        synthetic = False
    out = {"kind": cat, "data": data, "synthetic": synthetic}
    if cat == "dividend" and data.get("amount_per_share") and last_close:
        out["yield_pct"] = data["amount_per_share"] / last_close * 100
    if cat == "management_change":
        who = data.get("name") or "Executive"
        act = data.get("action") or "changed"
        role = data.get("role") or "role"
        out["headline"] = f"{role} {act}"
        out["flag"] = "No successor named" if act in ("resigned", "retired") and not data.get("successor") else None
    out["line"] = one_liner(cat, data, out)
    return out


def one_liner(cat: str, d: dict, out: dict) -> str:
    g = lambda k: d.get(k)
    if cat == "dividend" and g("amount_per_share"):
        y = f" (yield {out['yield_pct']:.1f}%)" if out.get("yield_pct") else ""
        return f"Dividend ₹{g('amount_per_share'):g} per share{y}" + (f", record date {g('record_date')}" if g("record_date") else "")
    if cat == "management_change":
        return f"{g('name') or 'Executive'}: {out['headline']}" + (f". {out['flag']}" if out.get("flag") else "")
    if cat == "credit_rating" and (g("old") or g("new")):
        return f"{g('agency') or 'Agency'}: {g('old') or '?'} → {g('new') or '?'}" + (f", outlook {g('outlook')}" if g("outlook") else "")
    if cat == "press_release" and g("fact"):
        return g("fact")
    size = g("size_crore") or g("amount_crore")
    if size:
        return f"{cat.replace('_', ' ').title()}: ₹{size:g} Cr"
    return ""
