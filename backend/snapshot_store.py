"""X-14: a frozen copy of the database, committed under data/, used only as a fallback."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from . import config, db

SNAP = Path(__file__).resolve().parent.parent / "data" / "snapshot.db"


def save() -> str:
    """Copy the live database into data/snapshot.db (consistent copy via SQLite backup)."""
    SNAP.parent.mkdir(exist_ok=True)
    src = sqlite3.connect(config.db_path())
    dst = sqlite3.connect(SNAP)
    src.backup(dst)
    with dst:
        dst.execute("INSERT INTO meta(key,value) VALUES ('snapshot_saved_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (db.now_iso(),))
        dst.execute("UPDATE meta SET value='snapshot' WHERE key='data_mode' AND value='live'")
    src.close(); dst.close()
    return str(SNAP)


def load() -> bool:
    """Replace the working database with the frozen snapshot. Returns False if there is none."""
    if not SNAP.exists():
        return False
    Path(config.db_path()).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SNAP, config.db_path())
    return True
