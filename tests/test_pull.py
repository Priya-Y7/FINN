import os, tempfile
os.environ["FINN_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "r.db")
os.environ["FINN_MOCK_LLM"] = "1"
from datetime import date
import pandas as pd, pytest
from backend import db
from backend.pull import ask, bullbear, docs, financials, periods, promises as P, research, retrieval, sample_pull, snapshot

TODAY = date(2026, 11, 14)
ANN = pd.DataFrame({"sales": [1000, 1100], "operating_profit": [150, 176], "pat": [80, 90], "borrowings": [500, 420]}, index=["2025-03", "2026-03"])
CHUNK = {"id": "T-Q2FY26-p1-c1", "text": "We expect operating margin of 18% for FY26. We will bring borrowings down to 400 crore by FY26. "
         "We expect double-digit PAT growth in FY27."}


def test_fiscal_labels():
    assert periods.quarter_label(2025, 9) == "Q2 FY26 (Jul-Sep 2025)"
    assert periods.quarter_label(2026, 3) == "Q4 FY26 (Jan-Mar 2026)"
    assert docs.transcript_period("Aug 2026") == "Q1FY27" and docs.transcript_period("May 2026") == "Q4FY26"


def test_cagr():
    assert snapshot.cagr(200, 100, 5) == pytest.approx((2 ** 0.2 - 1) * 100)
    assert snapshot.cagr(200, 0, 5) is None


def test_promise_scoring_by_hand():
    ps = [P.normalise(p) for p in P.heuristic_extract([CHUNK])]
    kept, dropped = P.verify(ps, {CHUNK["id"]: CHUNK})
    assert dropped == 0 and len(kept) == 3
    s = {p["metric"]: P.score(p, ANN, None, TODAY) for p in kept}
    assert s["op_margin"]["actual"] == pytest.approx(16.0) and s["op_margin"]["status"] == "missed"   # 16/18 = 0.89 < 0.9
    assert s["op_margin"]["gap_bps"] == pytest.approx(-200)
    assert s["borrowings"]["status"] == "partly"          # lower is better: 400/420 = 0.952
    assert s["pat_growth"]["status"] == "not_due" and s["pat_growth"]["target_low"] == 10   # "double-digit" -> at least 10%


def test_delivery_rate_formula():
    dr = P.delivery_rate([{"status": s} for s in ["delivered", "delivered", "partly", "missed", "not_due", "cant_verify"]])
    assert dr["rate"] == pytest.approx((2 + 0.5) / 4) and dr["based_on"] == 4


def test_fabricated_quote_or_number_is_dropped():
    bad_quote = {"metric": "op_margin", "kind": "numeric", "target_low": 18.0, "quote": "We guarantee margins of 40%.", "source_id": CHUNK["id"]}
    bad_number = {"metric": "op_margin", "kind": "numeric", "target_low": 25.0, "quote": "We expect operating margin of 18% for FY26.", "source_id": CHUNK["id"]}
    no_chunk = {"metric": "op_margin", "kind": "numeric", "target_low": 18.0, "quote": "x", "source_id": "T-nope"}
    kept, dropped = P.verify([bad_quote, bad_number, no_chunk], {CHUNK["id"]: CHUNK})
    assert kept == [] and dropped == 3


def test_cant_verify_never_guesses():
    p = P.normalise({"metric": "capex", "kind": "numeric", "target_low": 500.0, "horizon": "FY26", "quote": "capex of 500 crore"})
    assert P.score(p, ANN, None, TODAY)["status"] == "cant_verify"          # no capex column
    q = {"metric": "op_margin", "kind": "qualitative", "horizon": None}
    assert P.score(q, ANN, None, TODAY)["status"] == "cant_verify"


def test_bullbear_guard_rejects_uncited_and_foreign_ids():
    ok = {"bull": [{"text": "a", "ids": ["FIN"]}] * 3, "bear": [{"text": "b", "ids": ["X1"]}] * 3}
    assert bullbear.validate(ok, {"FIN", "X1"}) == []
    assert bullbear.validate(ok, {"FIN"})                                   # X1 not in packet
    assert bullbear.validate({"bull": [{"text": "a", "ids": []}] * 3, "bear": ok["bear"]}, {"FIN", "X1"})
    assert bullbear.validate({"bull": ok["bull"][:2], "bear": ok["bear"]}, {"FIN", "X1"})   # needs exactly 3


def test_ask_drops_uncited_sentences():
    kept, all_ok = ask.validate("Margins fell [T-1]. This sentence has no citation. Debt rose [T-9].", {"T-1"})
    assert [k["ids"] for k in kept] == [["T-1"]] and not all_ok


def test_screener_table_parser_fixture():
    # Hand-written approximation of screener.in markup; tests our parsing logic only.
    html = """<section id="profit-loss"><table><thead><tr><th></th><th>Mar 2025</th><th>Mar 2026</th></tr></thead><tbody>
      <tr><td class="text">Sales&nbsp;+</td><td>1,000</td><td>1,100</td></tr>
      <tr><td class="text">Operating Profit</td><td>150</td><td>176</td></tr>
      <tr><td class="text">Net Profit +</td><td>80</td><td>90</td></tr></tbody></table></section>"""
    rows = financials.parse_tables(html)
    got = {(r["period_end"], r["metric"]): r["value"] for r in rows}
    assert got[("2026-03", "sales")] == 1100 and got[("2025-03", "pat")] == 80


def test_end_to_end_on_sample_data_and_cache():
    db.init_db(); sample_pull.generate()
    r = research.run("SUZLON", today=TODAY)
    assert r["promises"]["available"] and r["bull_bear"]["available"] and r["snapshot"]["available"]
    assert research.run("SUZLON", today=TODAY)["cached"] is True
    with db.session() as conn:
        chunks = retrieval.load_chunks(conn, "SUZLON")
        ids = {c["id"] for c in chunks}
    for p in r["promises"]["promises"]:
        assert p["source_id"] in ids                                         # every promise cites a real chunk
    for pt in r["bull_bear"]["bull"] + r["bull_bear"]["bear"]:
        assert pt["ids"] and all(i in ids or i == "FIN" for i in pt["ids"])
    a = ask.answer("SUZLON", "What are the main risks?", chunks, "h")
    assert a["found"] and all(i in ids for s in a["answer"] for i in s["ids"])
    assert ask.answer("SUZLON", "zzzz qqqq", chunks, "h")["text"] == ask.NOT_FOUND


def test_real_world_phrasing_horizon_numbers_and_dedupe():
    c = {"id": "T-Q4FY24-p1-c1", "text": "We expect operating margin of 18-19% in FY2024. We will invest Rs 2,800 crore as capex. "
         "We expect revenue growth of 10-20% in FY2024. We expect operating margin of 18-19% in FY2024."}
    ps = [dict(p, call="Q4FY24") for p in P.heuristic_extract([c])]
    kept, dropped = P.verify(ps, {c["id"]: c})
    assert dropped == 0
    got = {(p["metric"], p["target_low"], p["target_high"], P.normalise(p)["horizon"]) for p in kept}
    assert ("op_margin", 18.0, 19.0, "FY24") in got and ("revenue_growth", 10.0, 20.0, "FY24") in got
    assert ("capex", 2800.0, 2800.0, "FY25") in got       # no stated period after a Q4 call: the coming year
    assert P.norm_horizon("FY2024-25") == "FY25" and P.norm_horizon("Q3 FY2025") == "Q3FY25"
