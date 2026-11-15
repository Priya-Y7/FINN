"""SYNTHETIC annual/quarterly financials and concall text so Pull can be run and tested offline.

Everything is labelled [SAMPLE] (documents) or is_sample=1 (financials). Targets in the fake calls are set
relative to the fake actuals, so the scorecard shows a mix of delivered / partly / missed.
"""
from __future__ import annotations

import hashlib

import numpy as np

from .. import config, db
from . import docs, financials

CALLS = [("Q2FY26", "Nov 2025"), ("Q3FY26", "Feb 2026"), ("Q4FY26", "May 2026"), ("Q1FY27", "Aug 2026")]


def _rng(t: str, salt: str = "") -> np.random.Generator:
    return np.random.default_rng(int(hashlib.sha256((t + salt).encode()).hexdigest()[:8], 16))


def make_financials(ticker: str, bank: bool = False):
    r = _rng(ticker, "fin")
    g, m0, drift = r.uniform(0.06, 0.18), r.uniform(14, 24), r.uniform(-1.2, 0.6)
    annual, sales, borrow, res = [], float(r.uniform(2000, 40000)), float(r.uniform(500, 9000)), float(r.uniform(3000, 20000))
    cc = r.uniform(0.5, 1.3)
    rows = []
    for i, yr in enumerate(range(2017, 2027)):
        sales *= 1 + g + r.normal(0, 0.03)
        margin = max(6.0, m0 + drift * i + r.normal(0, 0.8))
        op = sales * margin / 100
        dep, intr = sales * 0.04, borrow * 0.08
        pbt = op - dep - intr
        pat = pbt * 0.75
        borrow *= 1 + r.normal(0.02, 0.08)
        res += pat * 0.7
        capex = sales * r.uniform(0.03, 0.07)
        vals = {"sales": sales, "operating_profit": op, "pat": pat, "borrowings": borrow, "equity_capital": 100.0, "reserves": res,
                "cfo": pat * cc * r.uniform(0.85, 1.15), "capex": -capex, "roce_pct": r.uniform(10, 22),
                "debtor_days": r.uniform(30, 70), "inventory_days": r.uniform(40, 90), "payable_days": r.uniform(30, 60)}
        for k, v in vals.items():
            rows.append({"freq": "A", "period_end": f"{yr}-03", "metric": k, "value": round(float(v), 1)})
        annual.append(vals)
    # quarterly: 12 quarters ending Sep 2026; for one ticker in three, margin and sales slide in the last 3 quarters
    slide = int(hashlib.sha256(ticker.encode()).hexdigest()[:2], 16) % 3 == 0
    qs, qm = annual[-1]["sales"] / 4, annual[-1]["operating_profit"] / annual[-1]["sales"] * 100
    ends = [(2023, 12), (2024, 3), (2024, 6), (2024, 9), (2024, 12), (2025, 3), (2025, 6), (2025, 9), (2025, 12), (2026, 3), (2026, 6), (2026, 9)]
    for k, (y, mo) in enumerate(ends):
        f = 1 + g / 4 * (k - 8) + r.normal(0, 0.01)
        s, mg = qs * f, qm + r.normal(0, 0.4)
        if slide and k >= 9:
            s, mg = qs * (1 + g / 4 * 1.0) * (1 - 0.03 * (k - 8)), qm + 0.5 - 0.9 * (k - 8)
        for kk, v in {"sales": s, "operating_profit": s * mg / 100, "pat": s * mg / 100 * 0.45}.items():
            rows.append({"freq": "Q", "period_end": f"{y}-{mo:02d}", "metric": kk, "value": round(float(v), 1)})
    return rows, annual, slide


def _call_text(ticker: str, name: str, annual: list[dict], slide: bool) -> dict[str, str]:
    r = _rng(ticker, "calls")
    a, p = annual[-1], annual[-2]
    act_m = a["operating_profit"] / a["sales"] * 100
    act_g = (a["sales"] / p["sales"] - 1) * 100
    act_capex = abs(a["capex"])
    act_b = a["borrowings"]
    t_m, t_g = act_m * r.uniform(0.9, 1.1), max(3.0, act_g * r.uniform(0.85, 1.12))
    t_capex, t_b = act_capex * r.uniform(0.9, 1.15), act_b * r.uniform(0.85, 1.1)
    soften = r.random() < 0.6
    glow = "Demand remains strong and we are confident margins are improving. " if slide else "Demand remains healthy across our segments. "
    filler = f"Good morning everyone and welcome to the {name} earnings call. "
    qa = "We will now begin the question and answer session.\nAnalyst: Could you talk about the outlook and any risks you see?\nCFO: "
    return {
        "Q2FY26": f"Moderator: {filler}\nCEO: We expect operating margin of {t_m:.0f}% for FY26. We are guiding to revenue growth of {t_g:.0f}% in FY26. "
                  f"Management targets capex of {t_capex:.0f} crore in FY26.\n{qa}Capex plans are on track and input costs are a risk we are watching.",
        "Q3FY26": f"Moderator: {filler}\nCEO: We now expect operating margin of {(t_m * (0.93 if soften else 1.0)):.0f}% for FY26. "
                  f"We will bring borrowings down to {t_b:.0f} crore by FY26. {glow}\n{qa}Competition is intensifying in some segments.",
        "Q4FY26": f"Moderator: {filler}\nCEO: We expect double-digit revenue growth in FY27. We aim for operating margin of {act_m * 1.05 + 1:.0f}% by FY28. "
                  f"{glow}\n{qa}Our balance sheet remains healthy and capex discipline continues.",
        "Q1FY27": f"Moderator: {filler}\nCEO: We expect PAT growth of 15% in FY27. We are confident that operating margin will improve in FY27. {glow}\n"
                  f"{qa}The outlook depends on demand and commodity prices, which are risks.",
    }


def _ar_text(name: str) -> str:
    return (f"MANAGEMENT DISCUSSION AND ANALYSIS\n{name} operates across several segments. The outlook for the coming year remains constructive, "
            f"supported by demand and capacity additions. " * 4 + "\nRISK FACTORS\nKey risks include competition, commodity price volatility, regulatory change and "
            "execution delays on capital projects. Rising debt would pressure returns. " * 4)


def generate() -> dict:
    n = 0
    with db.session() as conn:
        conn.execute("DELETE FROM financials WHERE is_sample=1")
        for c in config.all_companies():
            t = c["ticker"]
            rows, annual, slide = make_financials(t, bool(c.get("is_bank")))
            financials.save(conn, t, rows, is_sample=True)
            conn.execute("DELETE FROM chunks WHERE document_id IN (SELECT id FROM documents WHERE ticker=? AND url LIKE 'sample://%')", (t,))
            conn.execute("DELETE FROM documents WHERE ticker=? AND url LIKE 'sample://%'", (t,))
            texts = _call_text(t, c["name"], annual, slide)
            for code, month in CALLS:
                did = f"sample-{t}-{code}"
                conn.execute("INSERT OR REPLACE INTO documents(id,ticker,doc_type,period,title,url,sha256,fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                             (did, t, "transcript", code, f"[SAMPLE] {code} earnings call transcript", f"sample://{t}/{code}",
                              hashlib.sha256(texts[code].encode()).hexdigest(), db.now_iso()))
                for ch in docs.chunk_transcript(code, [texts[code]]):
                    conn.execute("INSERT OR REPLACE INTO chunks(id,document_id,page,section,text) VALUES (?,?,?,?,?)", (ch["id"], did, ch["page"], ch["section"], ch["text"]))
            ar = _ar_text(c["name"])
            conn.execute("INSERT OR REPLACE INTO documents(id,ticker,doc_type,period,title,url,sha256,fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                         (f"sample-{t}-AR", t, "annual_report", "FY25", "[SAMPLE] Annual report FY25", f"sample://{t}/AR", hashlib.sha256(ar.encode()).hexdigest(), db.now_iso()))
            for ch in docs.chunk_report("FY25", [ar]):
                conn.execute("INSERT OR REPLACE INTO chunks(id,document_id,page,section,text) VALUES (?,?,?,?,?)", (ch["id"], f"sample-{t}-AR", ch["page"], ch["section"], ch["text"]))
            n += 1
    return {"companies": n}
