"""Records every job run, so the app can show when data was last refreshed and what failed."""
from __future__ import annotations

import traceback
from contextlib import contextmanager

from . import db


class JobHandle:
    def __init__(self) -> None:
        self.rows = 0
        self.notes: list[str] = []

    def note(self, message: str) -> None:
        self.notes.append(message)


@contextmanager
def job(name: str):
    """Usage: with job('ingest_prices') as j: ...; j.rows += n. Errors are logged, then re-raised."""
    with db.session() as conn:
        cur = conn.execute(
            "INSERT INTO job_runs(name, started_at, status) VALUES (?,?, 'running')", (name, db.now_iso())
        )
        run_id = cur.lastrowid
    handle = JobHandle()
    try:
        yield handle
    except Exception as exc:  # noqa: BLE001
        with db.session() as conn:
            conn.execute(
                "UPDATE job_runs SET finished_at=?, status='error', rows=?, error=? WHERE id=?",
                (db.now_iso(), handle.rows, f"{exc}\n{traceback.format_exc(limit=3)}"[:2000], run_id),
            )
        raise
    else:
        with db.session() as conn:
            note = "; ".join(handle.notes)[:2000] or None
            conn.execute(
                "UPDATE job_runs SET finished_at=?, status='ok', rows=?, error=? WHERE id=?",
                (db.now_iso(), handle.rows, note, run_id),
            )
