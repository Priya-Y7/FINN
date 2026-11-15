"""Record annual-report and concall-transcript links from screener.in (download/parse comes in Pull)."""
from __future__ import annotations

import hashlib

from .. import config, db
from ..joblog import job
from ..sources import SourceError, screener


def run(tickers: list[str] | None = None) -> dict:
    wanted = tickers or [c["ticker"] for c in config.all_companies()]
    report = {}
    with job("fetch_documents") as j:
        for t in wanted:
            try:
                docs = screener.fetch_documents(t)
            except SourceError as exc:
                report[t] = {"error": str(exc)}
                continue
            with db.session() as conn:
                for kind, key in (("annual_report", "annual_reports"), ("transcript", "transcripts")):
                    for d in docs[key]:
                        did = hashlib.sha256(f"{t}|{d['url']}".encode()).hexdigest()[:20]
                        conn.execute(
                            """INSERT OR IGNORE INTO documents(id,ticker,doc_type,period,title,url)
                               VALUES (?,?,?,?,?,?)""",
                            (did, t, kind, d["period"], d["title"], d["url"]))
                        j.rows += 1
            report[t] = {"annual_reports": len(docs["annual_reports"]), "transcripts": len(docs["transcripts"])}
        if all("error" in r for r in report.values()):
            raise SourceError("no documents fetched from screener.in")
    return report
