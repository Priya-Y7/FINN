"""Fetch recent announcements: NSE first, BSE as the fallback per company."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .. import config, db
from ..joblog import job
from ..sources import SourceError, bse
from ..sources.nse import NseClient
from .store import save_announcements


def run(days: int | None = None) -> dict:
    days = days or config.settings()["jobs"]["announcements_lookback_days"]
    to_d = datetime.now(timezone.utc)
    from_d = to_d - timedelta(days=days)
    nse, report = NseClient(), {}
    with job("ingest_announcements") as j:
        for c in config.all_companies():
            items, used, errs = [], None, []
            try:
                items, used = nse.announcements(c["ticker"], from_d, to_d), "nse"
            except SourceError as exc:
                errs.append(f"nse: {exc}")
                try:
                    items, used = bse.announcements(c["ticker"], c.get("bse_code"), from_d, to_d), "bse"
                except SourceError as exc2:
                    errs.append(f"bse: {exc2}")
            if used:
                with db.session() as conn:
                    j.rows += save_announcements(conn, items)
            report[c["ticker"]] = {"source": used, "count": len(items), "errors": errs}
        got = [t for t, r in report.items() if r["source"]]
        j.note(f"{len(got)}/{len(report)} companies reached")
        if not got:
            raise SourceError("no announcements fetched from NSE or BSE")
        with db.session() as conn:
            db.set_meta(conn, "announcements_refreshed_at", db.now_iso())
    return report
