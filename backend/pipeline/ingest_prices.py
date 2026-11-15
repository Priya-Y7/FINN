"""Fetch end-of-day prices for every company; recompute metrics and holdings."""
from __future__ import annotations

from .. import config, db, holdings
from ..joblog import job
from ..sources import SourceError, yahoo
from .store import save_prices


def run() -> dict:
    ok, failed = [], {}
    with job("ingest_prices") as j:
        known = config.all_companies()
        with db.session() as conn:      # companies the user added from the Ask tab
            extra = [{"ticker": r["ticker"], "yahoo_symbol": r["yahoo_symbol"]} for r in conn.execute(
                "SELECT ticker,yahoo_symbol FROM companies") if r["ticker"] not in {k["ticker"] for k in known}]
        for c in known + extra:
            try:
                df = yahoo.fetch_history(c["yahoo_symbol"])
            except SourceError as exc:
                failed[c["ticker"]] = str(exc)
                continue
            with db.session() as conn:
                j.rows += save_prices(conn, c["ticker"], df)
            ok.append(c["ticker"])
        if ok:
            with db.session() as conn:
                holdings.compute_holdings(conn)
                db.set_meta(conn, "data_mode", "live")
                db.set_meta(conn, "prices_refreshed_at", db.now_iso())
        j.note(f"{len(ok)} ok, {len(failed)} failed")
        if failed and not ok:
            raise SourceError("no prices fetched: " + "; ".join(f"{k}: {v}" for k, v in list(failed.items())[:3]))
    return {"ok": ok, "failed": failed}
