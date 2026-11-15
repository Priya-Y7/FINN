"""SQLite storage. One small file holds everything the app reads."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    ticker TEXT PRIMARY KEY,
    yahoo_symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    sector TEXT,
    size TEXT,
    is_bank INTEGER NOT NULL DEFAULT 0,
    bse_code TEXT,
    in_portfolio INTEGER NOT NULL DEFAULT 0,
    weight REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS holdings (
    ticker TEXT PRIMARY KEY REFERENCES companies(ticker),
    qty REAL NOT NULL,
    start_date TEXT NOT NULL,
    start_price REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT NOT NULL REFERENCES companies(ticker),
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    ret_pct REAL,       -- daily return %, adjusted prices
    vol_ratio REAL,     -- volume / mean volume of previous N days
    z_ret REAL,         -- return z-score vs previous N daily returns
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS announcements (
    id TEXT PRIMARY KEY,                 -- hash(ticker, timestamp, title)
    ticker TEXT NOT NULL,
    ts TEXT NOT NULL,                    -- UTC ISO timestamp
    source TEXT NOT NULL,                -- nse | bse | sample
    title TEXT NOT NULL,
    category_text TEXT,
    pdf_url TEXT,
    category TEXT,                       -- filled by the Push stage
    tier INTEGER,
    score REAL,
    summary TEXT,
    enrichment_json TEXT,
    is_sample INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ann_ticker_ts ON announcements(ticker, ts);
CREATE INDEX IF NOT EXISTS idx_ann_ts ON announcements(ts);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    doc_type TEXT NOT NULL,              -- annual_report | transcript
    period TEXT,
    title TEXT,
    url TEXT NOT NULL,
    sha256 TEXT,
    local_path TEXT,
    fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_doc_ticker ON documents(ticker, doc_type);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT NOT NULL,                    -- e.g. T-Q2FY26-p7-c3, unique within a company's documents
    document_id TEXT NOT NULL REFERENCES documents(id),
    page INTEGER,
    section TEXT,
    text TEXT NOT NULL,
    PRIMARY KEY (document_id, id)
);

CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,                  -- price | volume | announcement | confirmed
    tickers_json TEXT,
    params_json TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts_fired (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail_json TEXT,
    status TEXT NOT NULL DEFAULT 'new',  -- new | seen | dismissed
    created_at TEXT NOT NULL,
    UNIQUE (rule_id, ticker, date, kind)
);

CREATE TABLE IF NOT EXISTS analysis_cache (
    key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    value_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    status TEXT NOT NULL,
    step TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,                -- running | ok | error
    rows INTEGER DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    task TEXT NOT NULL,
    model_class TEXT NOT NULL,
    model TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cached INTEGER NOT NULL DEFAULT 0,
    mock INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS financials (
    ticker TEXT NOT NULL,
    freq TEXT NOT NULL,                  -- A annual | Q quarterly
    period_end TEXT NOT NULL,            -- YYYY-MM
    metric TEXT NOT NULL,                -- sales, operating_profit, pat, borrowings, equity, reserves, cfo, capex, ...
    value REAL,
    is_sample INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ticker, freq, period_end, metric)
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables and seed the companies table from config (idempotent)."""
    with session() as conn:
        conn.executescript(SCHEMA)
        for c in config.all_companies():
            conn.execute(
                """INSERT INTO companies
                   (ticker, yahoo_symbol, name, sector, size, is_bank, bse_code, in_portfolio, weight)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(ticker) DO UPDATE SET
                     yahoo_symbol=excluded.yahoo_symbol, name=excluded.name, sector=excluded.sector,
                     size=excluded.size, is_bank=excluded.is_bank, bse_code=excluded.bse_code,
                     in_portfolio=excluded.in_portfolio, weight=excluded.weight""",
                (c["ticker"], c["yahoo_symbol"], c["name"], c.get("sector"), c.get("size"),
                 1 if c.get("is_bank") else 0, c.get("bse_code"), c["in_portfolio"], c["weight"]),
            )


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
