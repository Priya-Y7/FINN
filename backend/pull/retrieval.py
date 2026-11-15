"""R-05: BM25 keyword ranking plus cue filters. No vector database."""
from __future__ import annotations

import re

from rank_bm25 import BM25Plus

CUE = re.compile(r"\b(expect|expects|expected|guide|guidance|target|targets|will be|will reach|aim|aims|aspire|plan to|"
                 r"by fy ?\d{2}|going forward|outlook|confident|double[- ]digit|improve|improving)\b", re.I)
TOKEN = re.compile(r"[a-z0-9]+")
STOP = {"the", "a", "an", "of", "to", "in", "is", "and", "for", "on", "what", "why", "how", "did", "do", "does", "was", "were", "this", "that", "it", "with", "at", "by"}


def tok(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


def load_chunks(conn, ticker: str) -> list[dict]:
    rows = conn.execute(
        """SELECT c.id, c.page, c.section, c.text, d.doc_type, d.period, d.title, d.url
           FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.ticker=? ORDER BY d.period DESC, c.page""", (ticker,)).fetchall()
    return [dict(r) for r in rows]


def cue_chunks(chunks: list[dict]) -> list[dict]:
    return [c for c in chunks if CUE.search(c["text"])]


class Index:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.bm25 = BM25Plus([tok(c["text"]) or ["_"] for c in chunks]) if chunks else None

    def search(self, query: str, k: int = 8, doc_type: str | None = None, min_score: float = 0.0) -> list[dict]:
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(tok(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        out = []
        for i in order:
            if scores[i] <= min_score:
                break
            if doc_type and self.chunks[i]["doc_type"] != doc_type:
                continue
            out.append({**self.chunks[i], "score": float(scores[i])})
            if len(out) == k:
                break
        return out


def source_label(c: dict) -> str:
    """Chip text such as 'AR FY25 p.42' or 'Call Q2FY26 p.7'."""
    kind = {"annual_report": "AR", "filing": "Filing"}.get(c["doc_type"], "Call")
    return f"{kind} {c['period']} p.{c['page']}"
