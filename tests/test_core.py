import os, tempfile
import numpy as np, pandas as pd, pytest

os.environ["FINN_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["FINN_MOCK_LLM"] = "1"

from backend import db, holdings
from backend.metrics import add_metrics
from backend.sources import bse, nse, screener
from backend.pipeline import sample_data


def test_metrics_formulas():
    closes = [100 + i for i in range(25)] + [140]
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=26).strftime("%Y-%m-%d"),
                       "close": closes, "volume": [1000] * 25 + [5000]})
    m = add_metrics(df, 20)
    assert m.ret_pct.iloc[-1] == pytest.approx((140 / 124 - 1) * 100)
    assert m.vol_ratio.iloc[-1] == pytest.approx(5.0)          # today excluded from the mean
    prev = m.ret_pct.iloc[-21:-1]
    assert m.z_ret.iloc[-1] == pytest.approx((m.ret_pct.iloc[-1] - prev.mean()) / prev.std(ddof=1))
    assert np.isnan(m.z_ret.iloc[5])                            # not enough history yet


def test_sample_holdings_and_portfolio():
    db.init_db()
    sample_data.generate(force=True)
    with db.session() as conn:
        v = holdings.portfolio_view(conn)
        assert len(v["positions"]) == 20
        assert sum(p["weight"] for p in v["positions"]) == pytest.approx(100)
        assert conn.execute("SELECT COUNT(*) c FROM announcements WHERE is_sample=0").fetchone()["c"] == 0
        assert db.get_meta(conn, "data_mode") == "sample"


def test_sample_refuses_to_overwrite_live():
    with db.session() as conn:
        db.set_meta(conn, "data_mode", "live")
    with pytest.raises(RuntimeError):
        sample_data.generate()
    with db.session() as conn:
        db.set_meta(conn, "data_mode", "sample")


# NOTE: fixtures below are hand-written approximations of the live payloads (live sources were
# unreachable when this was built). They test our parsing logic, not the real API shape.
def test_parse_nse_fixture():
    payload = [{"symbol": "SBIN", "desc": "Financial Results", "attchmntText": "Results for Q2",
                "an_dt": "13-Nov-2026 16:05:10", "attchmntFile": "https://x/y.pdf"},
               {"desc": "bad row", "an_dt": "garbage"}]
    out = nse.parse_announcements(payload, "sbin")
    assert len(out) == 1 and out[0]["ts"] == "2026-11-13T10:35:10Z" and out[0]["pdf_url"].endswith("y.pdf")


def test_parse_bse_fixture():
    payload = {"Table": [{"NEWS_DT": "2026-11-13T16:05:10.123", "NEWSSUB": "Board Meeting", "CATEGORYNAME": "Board Meeting", "ATTACHMENTNAME": "a.pdf"}]}
    out = bse.parse_announcements(payload, "SBIN")
    assert out[0]["ts"] == "2026-11-13T10:35:10Z" and out[0]["pdf_url"].endswith("AttachLive/a.pdf")


def test_parse_screener_fixture():
    html = """<section id="documents"><div class="annual-reports"><ul>
      <li><a href="/a.pdf">Financial Year 2026</a></li></ul></div>
      <div class="concalls"><ul><li>Aug 2026 <a href="/t.pdf">Transcript</a> <a href="/p.pdf">PPT</a></li></ul></div></section>"""
    d = screener.parse_documents(html)
    assert d["annual_reports"][0]["period"] == "FY2026"
    assert len(d["transcripts"]) == 1 and d["transcripts"][0]["period"] == "Aug 2026"


def test_snapshot_only_blocks_live(monkeypatch):
    from backend.sources import SourceError, yahoo
    monkeypatch.setenv("USE_SNAPSHOT_ONLY", "1")
    with pytest.raises(SourceError):
        yahoo.fetch_history("SBIN.NS")


def test_snapshot_roundtrip(tmp_path, monkeypatch):
    from backend import snapshot_store
    monkeypatch.setattr(snapshot_store, "SNAP", tmp_path / "snapshot.db")
    db.init_db()
    with db.session() as conn:
        db.set_meta(conn, "data_mode", "live")
    snapshot_store.save()
    with db.session() as conn:
        db.set_meta(conn, "data_mode", "sample")
    assert snapshot_store.load()
    with db.session() as conn:
        assert db.get_meta(conn, "data_mode") == "snapshot"     # a frozen copy never claims to be live


def test_add_any_nse_ticker(tmp_path, monkeypatch):
    import pandas as pd
    from backend.pipeline import add_company as ac
    from backend.sources import yahoo, SourceError
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=40).strftime("%Y-%m-%d"), "open": 1.0, "high": 1.0, "low": 1.0, "close": range(100, 140), "volume": 1000})
    monkeypatch.setattr(yahoo, "fetch_history", lambda s, p=None: df if s == "ZZTEST.NS" else (_ for _ in ()).throw(SourceError("no price rows")))
    monkeypatch.setattr(ac, "_profile", lambda s: ("ZZ Test Ltd", "Industrials"))
    assert ac.add("zztest.ns") == {"ticker": "ZZTEST", "name": "ZZ Test Ltd", "added": True}
    assert ac.add("ZZTEST")["added"] is False
    import pytest
    with pytest.raises(SourceError):
        ac.add("NOSUCH")
    with pytest.raises(SourceError):
        ac.add("not valid!")
