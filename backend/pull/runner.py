"""Runs research in a background thread; a second viewer of the same company joins the running job (R-27)."""
from __future__ import annotations

import json
import threading
import time

from . import research

_runs: dict[str, dict] = {}
_lock = threading.Lock()


def start(ticker: str) -> dict:
    ticker = ticker.upper()
    with _lock:
        run = _runs.get(ticker)
        if run and not run["done"]:
            return run
        run = {"events": [], "done": False, "error": None}
        _runs[ticker] = run

    def emit(kind, data):
        run["events"].append((kind, data))

    def work():
        try:
            research.run(ticker, emit)
        except Exception as exc:  # noqa: BLE001
            run["error"] = str(exc)
            emit("error", {"text": str(exc)})
        finally:
            run["done"] = True
            emit("done", {})

    threading.Thread(target=work, daemon=True).start()
    return run


def stream(ticker: str):
    run = start(ticker)
    i = 0
    while True:
        while i < len(run["events"]):
            kind, data = run["events"][i]
            i += 1
            yield f"event: {kind}\ndata: {json.dumps(data, default=str)}\n\n"
            if kind == "done":
                return
        time.sleep(0.15)
