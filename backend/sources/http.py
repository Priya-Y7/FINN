"""One place for HTTP: headers, timeout, retries. Honours USE_SNAPSHOT_ONLY."""
from __future__ import annotations

import time

import requests

from .. import config
from . import SourceError


def snapshot_only() -> bool:
    return config.env_flag("USE_SNAPSHOT_ONLY")


BROWSER_HOSTS = ("nseindia.com", "nseindia.in", "bseindia.com")   # these reject Python's TLS fingerprint with 403


def new_session(extra_headers: dict | None = None, browser: bool = False):
    """browser=True: a session that presents Chrome's TLS fingerprint (curl_cffi), which NSE and BSE
    require. Falls back to plain requests if curl_cffi is not installed."""
    cfg = config.settings()["http"]
    s = None
    if browser:
        try:
            from curl_cffi import requests as cr
            s = cr.Session(impersonate="chrome")     # sets Chrome's own User-Agent and headers
        except Exception:
            s = None
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": cfg["user_agent"]})
    s.headers.update({"Accept-Language": "en-US,en;q=0.9"})
    if extra_headers:
        s.headers.update(extra_headers)
    return s


def get(url: str, session: requests.Session | None = None, **kwargs) -> requests.Response:
    """GET with retries. Raises SourceError with a plain message on failure."""
    if snapshot_only():
        raise SourceError("USE_SNAPSHOT_ONLY is set: live sources are disabled")
    cfg = config.settings()["http"]
    if session is None:
        session = new_session(browser=any(h in url for h in BROWSER_HOSTS))
    sess = session
    last: Exception | None = None
    for attempt in range(cfg["retries"] + 1):
        try:
            resp = sess.get(url, timeout=cfg["timeout_seconds"], **kwargs)
            if resp.status_code == 200:
                return resp
            last = SourceError(f"HTTP {resp.status_code} from {url}")
            if resp.status_code in (401, 403, 404):  # retrying will not help
                break
        except Exception as exc:  # requests or curl_cffi errors
            last = SourceError(f"{type(exc).__name__}: {exc}")
        time.sleep(1.5 * (attempt + 1))
    raise last if isinstance(last, SourceError) else SourceError(str(last))
