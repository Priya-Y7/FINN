"""Result cache: every model result and parsed document is stored once, keyed by a content hash."""
from __future__ import annotations

import hashlib
import json
import sqlite3

from .db import now_iso


def cache_key(*parts) -> str:
    """Stable hash of any JSON-able parts, e.g. (document hash, prompt version, model class)."""
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cache_get(conn: sqlite3.Connection, key: str):
    row = conn.execute("SELECT value_json FROM analysis_cache WHERE key=?", (key,)).fetchone()
    return json.loads(row["value_json"]) if row else None


def cache_set(conn: sqlite3.Connection, key: str, kind: str, value) -> None:
    conn.execute(
        """INSERT INTO analysis_cache(key, kind, value_json, created_at) VALUES (?,?,?,?)
           ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, created_at=excluded.created_at""",
        (key, kind, json.dumps(value, ensure_ascii=False, default=str), now_iso()),
    )
