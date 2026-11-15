"""One refresh: prices, announcements, documents. Falls back to the stored snapshot when live fails."""
from __future__ import annotations

from .. import db
from ..sources import SourceError
from ..push import alerts, process
from . import fetch_documents, ingest_announcements, ingest_prices


def run() -> dict:
    result: dict = {}
    for name, fn in (("prices", ingest_prices.run), ("announcements", ingest_announcements.run),
                     ("documents", fetch_documents.run)):
        try:
            result[name] = {"status": "ok", "detail": fn()}
        except SourceError as exc:
            result[name] = {"status": "failed", "error": str(exc)}
    try:
        result["process"] = {"status": "ok", "detail": process.run()}
        result["alerts"] = {"status": "ok", "detail": alerts.evaluate()}
    except Exception as exc:  # noqa: BLE001
        result["process"] = {"status": "failed", "error": str(exc)}
    with db.session() as conn:
        mode = db.get_meta(conn, "data_mode")
        if all(result[k]["status"] == "failed" for k in ("prices", "announcements", "documents")) and mode == "live":
            db.set_meta(conn, "data_mode", "snapshot")  # serving the last good copy
    return result
