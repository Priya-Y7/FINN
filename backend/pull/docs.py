"""R-02..R-04: pick documents, download, extract text with page numbers, chunk with stable ids."""
from __future__ import annotations

import hashlib
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import config, db
from ..sources import SourceError
from ..sources.http import get
from .periods import MON, quarter_code, quarter_end_for_call

SPEAKER = re.compile(r"^\s*([A-Z][A-Za-z.'\- ]{2,40}?)\s*(?:\([^)]*\))?\s*:\s*(.*)$")
QA_MARK = re.compile(r"question[- ]and[- ]answer|q ?& ?a session|we will now begin the question", re.I)
HEADINGS = [("management discussion", "Management discussion"), ("risk", "Risks"), ("outlook", "Outlook"),
            ("financial statements", "Financial statements"), ("director", "Directors' report"), ("corporate governance", "Governance")]
MAX_WORDS = 520   # about 700 tokens


def transcript_period(raw: str | None) -> str | None:
    """screener shows the call month, e.g. 'Aug 2026'. Returns 'Q1FY27'."""
    m = re.match(r"\s*([A-Za-z]{3})\w*\s+(\d{4})", raw or "")
    if not m or m.group(1).title() not in MON:
        return None
    y, mo = quarter_end_for_call(int(m.group(2)), MON.index(m.group(1).title()) + 1)
    return quarter_code(y, mo)


def pick_documents(conn, ticker: str) -> dict:
    """Latest annual report and the last four transcripts (R-02)."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM documents WHERE ticker=?", (ticker,))]
    ars = [r for r in rows if r["doc_type"] == "annual_report"]
    trs = [r for r in rows if r["doc_type"] == "transcript"]
    for r in trs:
        r["code"] = transcript_period(r["period"]) or r["period"]
    trs.sort(key=lambda r: (r["code"][-2:], r["code"][:2]) if r["code"] and r["code"].startswith("Q") else ("", ""), reverse=True)
    ars.sort(key=lambda r: r["period"] or "", reverse=True)
    return {"annual_report": ars[:1], "transcripts": trs[:4]}


def download(url: str, seconds: int = 90) -> bytes:
    """GET with a hard time limit. A stalled download can otherwise wait forever, because the
    HTTP timeout restarts whenever any bytes arrive."""
    box: dict = {}

    def run() -> None:
        try:
            box["data"] = get(url).content
        except Exception as exc:  # noqa: BLE001
            box["err"] = exc

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(seconds)
    if th.is_alive():
        raise SourceError(f"download took longer than {seconds}s")
    if "err" in box:
        raise box["err"]
    return box["data"]


def extract_pages(pdf_bytes: bytes) -> list[str]:
    import pymupdf
    return [p.get_text() for p in pymupdf.open(stream=pdf_bytes, filetype="pdf")]


def _words(t: str) -> int:
    return len(t.split())


def chunk_transcript(code: str, pages: list[str]) -> list[dict]:
    """Split by speaker turn, tag remarks vs Q&A, merge turns up to ~MAX_WORDS."""
    turns, section = [], "remarks"
    for pno, text in enumerate(pages, 1):
        for line in text.splitlines():
            if QA_MARK.search(line):
                section = "qa"
            m = SPEAKER.match(line)
            if m:
                turns.append({"page": pno, "section": section, "speaker": m.group(1).strip(), "text": m.group(2)})
            elif turns and line.strip():
                turns[-1]["text"] += " " + line.strip()
            elif line.strip():
                turns.append({"page": pno, "section": section, "speaker": "", "text": line.strip()})
    chunks, cur, counter = [], None, {}
    for t in turns:
        if cur and cur["page"] == t["page"] and cur["section"] == t["section"] and _words(cur["text"]) + _words(t["text"]) <= MAX_WORDS:
            cur["text"] += f"\n{t['speaker']}: {t['text']}" if t["speaker"] else " " + t["text"]
            continue
        if cur:
            chunks.append(cur)
        cur = {"page": t["page"], "section": t["section"], "text": f"{t['speaker']}: {t['text']}" if t["speaker"] else t["text"]}
    if cur:
        chunks.append(cur)
    for c in chunks:
        counter[c["page"]] = counter.get(c["page"], 0) + 1
        c["id"] = f"T-{code}-p{c['page']}-c{counter[c['page']]}"
    return chunks


def chunk_report(code: str, pages: list[str]) -> list[dict]:
    chunks, section, counter = [], "Report", {}
    for pno, text in enumerate(pages, 1):
        for line in text.splitlines()[:6]:
            low = line.lower().strip()
            for key, name in HEADINGS:
                if low.startswith(key) or (len(low) < 60 and key in low and line.isupper()):
                    section = name
        words = text.split()
        for i in range(0, len(words), MAX_WORDS):
            body = " ".join(words[i:i + MAX_WORDS])
            if len(body) > 80:
                counter[pno] = counter.get(pno, 0) + 1
                chunks.append({"id": f"AR-{code}-p{pno}-c{counter[pno]}", "page": pno, "section": section, "text": body})
    return chunks


def ingest(ticker: str) -> dict:
    """Download, extract, chunk and store. Scanned PDFs are flagged not readable and skipped (no OCR)."""
    root = Path(config.db_path()).parent / "docs" / ticker
    root.mkdir(parents=True, exist_ok=True)
    with db.session() as conn:
        picked = pick_documents(conn, ticker)
    report = {"ok": [], "unreadable": [], "failed": []}
    jobs = [(kind, d) for kind in ("annual_report", "transcripts") for d in picked[kind]]

    def fetch(job):                      # all documents download in parallel, each with a hard limit
        try:
            return download(job[1]["url"])
        except Exception as exc:  # noqa: BLE001
            return exc

    with ThreadPoolExecutor(max_workers=5) as pool:
        downloaded = list(pool.map(fetch, jobs))
    for (kind, d), pdf in zip(jobs, downloaded):
        code = d["code"] if kind == "transcripts" else (d["period"] or "AR")
        if isinstance(pdf, Exception):
            report["failed"].append({"doc": d["title"], "error": str(pdf)})
            continue
        try:
            pages = extract_pages(pdf)
        except Exception as exc:  # noqa: BLE001
            report["failed"].append({"doc": d["title"], "error": str(exc)})
            continue
        if True:
            if sum(len(p) for p in pages) < 200:
                report["unreadable"].append(d["title"])
                continue
            path = root / f"{hashlib.sha256(pdf).hexdigest()[:12]}.pdf"
            path.write_bytes(pdf)
            chunks = chunk_transcript(code, pages) if kind == "transcripts" else chunk_report(code, pages)
            with db.session() as conn:
                conn.execute("UPDATE documents SET period=?, sha256=?, local_path=?, fetched_at=? WHERE id=?",
                             (code, hashlib.sha256(pdf).hexdigest(), str(path), db.now_iso(), d["id"]))
                conn.execute("DELETE FROM chunks WHERE document_id=?", (d["id"],))
                conn.executemany("INSERT OR REPLACE INTO chunks(id,document_id,page,section,text) VALUES (?,?,?,?,?)",
                                 [(c["id"], d["id"], c["page"], c["section"], c["text"]) for c in chunks])
            report["ok"].append({"doc": d["title"], "chunks": len(chunks)})
    return report
