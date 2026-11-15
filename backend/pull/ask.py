"""R-23/R-25: cited follow-up answers from company documents only."""
from __future__ import annotations

import hashlib
import json
import re

from .. import db, llm
from ..cache import cache_get, cache_key, cache_set
from .retrieval import Index, source_label

NOT_FOUND = "Not found in the company's documents."
SYSTEM = ("Answer using ONLY the numbered PASSAGES. Every sentence must end with one or more citations like [T-Q2FY26-p7-c3] using ids from the passages. "
          "No outside knowledge, no predictions, no price targets. If the passages do not answer the question, reply exactly: " + NOT_FOUND)
CITE = re.compile(r"\[([^\[\]]+)\]")
CAP = 10


def norm_q(q: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", q.lower())).strip()


def validate(text: str, allowed: set[str]) -> tuple[list[dict], bool]:
    """Keep only sentences that cite valid ids. Returns (sentences, all_kept)."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?\]])\s+(?!\[)", text.strip()) if s.strip()]
    kept = []
    for s in sents:
        ids = [i.strip() for m in CITE.findall(s) for i in m.split(",")]
        if ids and all(i in allowed for i in ids):
            kept.append({"text": CITE.sub("", s).strip(), "ids": ids})
    return kept, len(kept) == len(sents)


def extractive(question: str, hits: list[dict]) -> str:
    """No-API-key answer: quote the best-matching sentence from the top passages, with its citation."""
    qt = set(__import__("backend.pull.retrieval", fromlist=["tok"]).tok(question))
    best = []
    for h in hits[:3]:
        for s in re.split(r"(?<=[.!?])\s+", h["text"].replace("\n", " ")):
            overlap = len(qt & set(__import__("backend.pull.retrieval", fromlist=["tok"]).tok(s)))
            if overlap:
                best.append((overlap, s.strip(), h["id"]))
    best.sort(key=lambda x: -x[0])
    return " ".join(f"{s} [{i}]" for _, s, i in best[:2]) or NOT_FOUND


def answer(ticker: str, question: str, chunks: list[dict], doc_hash: str) -> dict:
    key = cache_key("ask", ticker, norm_q(question), doc_hash)
    with db.session() as conn:
        hit = cache_get(conn, key)
    if hit:
        return {**hit, "cached": True}
    hits = Index(chunks).search(question, k=8)
    if not hits:
        res = {"answer": [], "text": NOT_FOUND, "sources": {}, "found": False}
    else:
        allowed = {h["id"] for h in hits}
        prompt = "QUESTION: " + question + "\n\nPASSAGES:\n" + "\n\n".join(f"[{h['id']}] ({source_label(h)})\n{h['text'][:1200]}" for h in hits)
        r = llm.complete("ask", "strong", SYSTEM, prompt, cache_parts=[key], max_tokens=700, mock_response=extractive(question, hits))
        sents, _ = validate(r["text"], allowed)
        used = {i for s in sents for i in s["ids"]}
        res = {"answer": sents, "text": " ".join(s["text"] for s in sents) if sents else NOT_FOUND, "found": bool(sents),
               "sources": {h["id"]: {"label": source_label(h), "page": h["page"], "title": h["title"], "url": h["url"]} for h in hits if h["id"] in used},
               "by_model": not r["mock"]}
    with db.session() as conn:
        cache_set(conn, key, "ask", res)
    return {**res, "cached": False}
