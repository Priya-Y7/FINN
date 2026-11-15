import os, tempfile
os.environ["FINN_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "p.db")
os.environ["FINN_MOCK_LLM"] = "1"
import pytest
from backend import db
from backend.push import alerts, calc, classify, digest, process, score
from backend.pipeline import sample_data


def card(pat_now=150, tax=50):
    d = {"unit": "crore",
         "now": {"revenue": 1080, "other_income": 20, "finance_costs": 30, "depreciation": 50, "exceptional": 0, "pbt": 200, "tax": tax, "pat": pat_now},
         "qoq": {"revenue": 1000, "other_income": 15, "finance_costs": 30, "depreciation": 48, "exceptional": 0, "pbt": 180, "tax": 45, "pat": 135},
         "yoy": {"revenue": 1000, "other_income": 10, "finance_costs": 30, "depreciation": 45, "exceptional": 0, "pbt": 160, "tax": 38, "pat": 122}}
    return calc.build_card(d, False)


def test_results_hand_calculation():
    c = card()
    t = {x["key"]: x for x in c["tiles"]}
    assert t["ebitda"]["value"] == pytest.approx(260)            # 200 + 30 + 50 - 20
    assert t["pat"]["yoy_pct"] == pytest.approx((150 - 122) / 122 * 100)
    assert c["margin_change_bps_yoy"] == pytest.approx((260 / 1080 - (160 + 30 + 45 - 10) / 1000) * 10000)
    assert c["sentence"].startswith("PAT up 23% YoY on 8% revenue growth")


def test_corrupted_extraction_needs_review():
    assert card(pat_now=100)["needs_review"] is True             # PBT - tax != PAT


def test_units_and_negative_base():
    assert calc.to_crore(100, "lakh") == pytest.approx(1.0)
    assert calc.change_pct(10, -5) is None and calc.change_pct(10, 0) is None


def test_bank_card_uses_nii_ppop():
    col = lambda s: {"interest_earned": 1000 * s, "interest_expended": 600 * s, "other_income": 50 * s, "operating_expenses": 200 * s,
                     "pbt": 160 * s, "tax": 40 * s, "pat": 120 * s}
    c = calc.build_card({"unit": "crore", "now": col(1.1), "qoq": col(1.0), "yoy": col(1.0)}, True)
    keys = [t["key"] for t in c["tiles"]]
    assert keys == ["nii", "ppop", "pbt", "pat"]
    assert c["tiles"][0]["value"] == pytest.approx(440) and c["tiles"][1]["value"] == pytest.approx(440 + 55 - 220)


def test_score_known_results_filing():
    s = score.score("results", "", [(4.0, 2.5)], 8, 8)
    assert s["score"] == 90 + 0 + 20 + 10 and s["tier"] == 1
    assert score.score("agm_egm", "", [], None, 8)["tier"] == 3


def test_classification_and_severity():
    assert classify.rule_classify("Board Meeting", "Financial Results for quarter") == "results"
    assert classify.rule_classify("", "Resignation of Chief Financial Officer") == "management_change"
    pts, why = classify.severity("management_change", "resignation of chief financial officer")
    assert pts == 90 and "no successor" in why
    assert classify.severity("credit_rating", "rating downgraded")[0] == 85


def test_engine_idempotent_and_preview_matches():
    db.init_db(); sample_data.generate(force=True)
    with db.session() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM alerts_fired").fetchone()["c"] > 0   # sample generation already ran the engine
    assert alerts.evaluate()["created"] == 0
    with db.session() as conn:
        p = alerts.preview(conn, "volume", {"ratio": 2.0, "n": 20}, days=7)
        engine = conn.execute("SELECT COUNT(*) c FROM alerts_fired WHERE kind='volume'").fetchone()["c"]
        assert p["count"] == engine


def test_tiers_exclusive_and_dedupe():
    with db.session() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM announcements WHERE tier NOT IN (1,2,3) OR tier IS NULL").fetchone()["c"] == 0
        a = dict(conn.execute("SELECT * FROM announcements LIMIT 1").fetchone())
        conn.execute("INSERT INTO announcements(id,ticker,ts,source,title,pdf_url) VALUES ('dup',?,?, 'bse', ?, 'https://x/bse.pdf')", (a["ticker"], a["ts"], a["title"].upper()))
        assert process.dedupe(conn) == 1
        d = digest.build(conn, days=30, only_portfolio=False)
        assert sum(d["counts"].values()) == len(d["tiers"]["act_now"]) + len(d["tiers"]["worth_knowing"]) + len(d["tiers"]["routine"])
