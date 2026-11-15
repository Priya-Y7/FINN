"""Loads config/*.yaml and .env. Every other module gets its numbers and company list from here."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


def _load_env_file() -> None:
    """Tiny .env reader (no extra dependency). Real environment variables win."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


def _yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def settings() -> dict:
    return _yaml("settings.yaml")


@lru_cache(maxsize=1)
def portfolio() -> list[dict]:
    rows = _yaml("portfolio.yaml")["portfolio"]
    total = sum(r["weight"] for r in rows)
    if abs(total - 100) > 1e-6:
        raise ValueError(f"portfolio weights must sum to 100, got {total}")
    return rows


@lru_cache(maxsize=1)
def adhoc() -> list[dict]:
    return _yaml("adhoc.yaml")["adhoc"]


def yahoo_symbol(ticker: str) -> str:
    return ticker.upper() + settings()["prices"]["yahoo_suffix"]


def all_companies() -> list[dict]:
    """Portfolio first, then ad-hoc, each tagged with in_portfolio and a Yahoo symbol."""
    out = []
    for r in portfolio():
        out.append({**r, "in_portfolio": 1, "yahoo_symbol": yahoo_symbol(r["ticker"])})
    for r in adhoc():
        out.append({**r, "in_portfolio": 0, "weight": 0, "yahoo_symbol": yahoo_symbol(r["ticker"])})
    return out


def db_path() -> Path:
    override = os.environ.get("FINN_DB_PATH")
    p = Path(override) if override else ROOT / settings()["database"]["path"]
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def env_flag(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}
