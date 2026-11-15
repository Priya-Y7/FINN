"""Optional in-process scheduler (FINN_AUTO_REFRESH=1): announcements every 15 min in market hours,
prices once after the close. Production runs the same jobs from GitHub Actions or cron instead."""
from __future__ import annotations

import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config, db

IST = ZoneInfo("Asia/Kolkata")


def _market_hours(now: datetime) -> bool:
    j = config.settings()["jobs"]
    return now.weekday() < 5 and j["market_open_ist"] <= now.strftime("%H:%M") <= j["market_close_ist"]


def loop() -> None:
    last_ann, last_px_day = 0.0, None
    every = config.settings()["jobs"]["announcements_every_minutes"] * 60
    while True:
        try:
            with db.session() as conn:
                live = db.get_meta(conn, "data_mode") in ("live", "snapshot")
            now = datetime.now(IST)
            if live:
                from .pipeline import ingest_announcements, ingest_prices
                from .push import alerts, process
                if _market_hours(now) and time.time() - last_ann >= every:
                    last_ann = time.time()
                    ingest_announcements.run(); process.run(); alerts.evaluate()
                run_at = config.settings()["jobs"]["prices_run_at_ist"]
                if now.weekday() < 5 and now.strftime("%H:%M") >= run_at and last_px_day != now.date():
                    last_px_day = now.date()
                    ingest_prices.run(); process.run(); alerts.evaluate()
        except Exception:  # noqa: BLE001  a failed run is logged in job_runs; keep the loop alive
            pass
        time.sleep(60)


def start() -> None:
    threading.Thread(target=loop, daemon=True, name="finn-scheduler").start()
