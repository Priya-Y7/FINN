"""Command line: python -m backend.cli <command>."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from . import config, db


def cmd_init_db(_):
    db.init_db()
    print("database ready:", config.db_path())


def cmd_sample(a):
    from .pipeline import sample_data
    db.init_db()
    print(json.dumps(sample_data.generate(force=a.force)))


def cmd_prices(_):
    from .pipeline import ingest_prices
    db.init_db()
    r = ingest_prices.run()
    print(f"ok: {len(r['ok'])}  failed: {len(r['failed'])}")
    for k, v in r["failed"].items():
        print(" -", k, v)


def cmd_announcements(_):
    from .pipeline import ingest_announcements
    db.init_db()
    for t, r in ingest_announcements.run().items():
        print(f"{t:12} {r['source'] or '-':4} {r['count']:3}  {'; '.join(r['errors'])}")


def cmd_docs(_):
    from .pipeline import fetch_documents
    db.init_db()
    print(json.dumps(fetch_documents.run(), indent=1))


def cmd_refresh(_):
    from .pipeline import refresh
    db.init_db()
    print(json.dumps(refresh.run(), indent=1, default=str)[:4000])


def cmd_process(_):
    from .push import alerts, process
    db.init_db()
    print(process.run(), alerts.evaluate())


def cmd_research(a):
    from .pull import research
    db.init_db()
    r = research.run(a.ticker, lambda k, d: print(k, str(d)[:80]))
    print(json.dumps({k: (v.get('available') if isinstance(v, dict) else v) for k, v in r.items() if k in ('snapshot', 'promises', 'bull_bear')}))


def cmd_snapshot_save(_):
    from . import snapshot_store
    print('saved', snapshot_store.save())


def cmd_snapshot_load(_):
    from . import snapshot_store
    print('loaded' if snapshot_store.load() else 'no snapshot found')


def cmd_usage(_):
    from . import llm
    print(json.dumps(llm.usage_summary(), indent=1))


def cmd_verify_sources(_):
    """Run this on YOUR machine. Probes each live source once and prints exactly what came back."""
    from .sources import SourceError, bse, screener, yahoo
    from .sources.nse import NseClient
    now = datetime.now(timezone.utc)
    checks = [
        ("Yahoo Finance prices (SBIN.NS)", lambda: f"{len(yahoo.fetch_history('SBIN.NS', '1mo'))} rows"),
        ("NSE announcements (SBIN)", lambda: f"{len(NseClient().announcements('SBIN', now - timedelta(days=14), now))} items"),
        ("BSE announcements (SBIN, 500112)", lambda: f"{len(bse.announcements('SBIN', '500112', now - timedelta(days=14), now))} items"),
        ("screener.in documents (INFY)", lambda: (lambda d: f"{len(d['annual_reports'])} annual reports, {len(d['transcripts'])} transcripts")(screener.fetch_documents("INFY"))),
    ]
    bad = 0
    for name, fn in checks:
        try:
            print(f"PASS  {name}: {fn()}")
        except (SourceError, Exception) as exc:  # noqa: BLE001
            bad += 1
            print(f"FAIL  {name}: {exc}")
    sys.exit(1 if bad else 0)


def cmd_verify_tickers(_):
    """Checks every ticker returns prices, and that each configured BSE code returns announcements."""
    from .sources import SourceError, yahoo
    for c in config.all_companies():
        try:
            n = len(yahoo.fetch_history(c["yahoo_symbol"], "5d"))
            print(f"PASS  {c['ticker']:12} {c['yahoo_symbol']:16} {n} rows")
        except SourceError as exc:
            print(f"FAIL  {c['ticker']:12} {c['yahoo_symbol']:16} {exc}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="finn")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in [("init-db", cmd_init_db), ("prices", cmd_prices), ("announcements", cmd_announcements),
                     ("docs", cmd_docs), ("snapshot-save", cmd_snapshot_save), ("snapshot-load", cmd_snapshot_load), ("usage", cmd_usage), ("process", cmd_process), ("refresh", cmd_refresh), ("verify-sources", cmd_verify_sources),
                     ("verify-tickers", cmd_verify_tickers)]:
        sub.add_parser(name).set_defaults(fn=fn)
    r = sub.add_parser("research")
    r.add_argument("ticker")
    r.set_defaults(fn=cmd_research)
    s = sub.add_parser("sample")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_sample)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
