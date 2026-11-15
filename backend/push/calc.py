"""P-18 / P-19 / P-20: results maths, done in code (never by the model).

Inputs are the extracted figures per column. Columns: now (current quarter), qoq (preceding quarter),
yoy (same quarter last year). Units are converted to crore first.
"""
from __future__ import annotations

UNIT_TO_CRORE = {"crore": 1.0, "cr": 1.0, "lakh": 0.01, "lakhs": 0.01, "million": 0.1, "mn": 0.1,
                 "billion": 100.0, "bn": 100.0, "thousand": 0.0001, "rs": 1e-7, "inr": 1e-7}
COLS = ("now", "qoq", "yoy")
GENERAL_FIELDS = ["revenue", "other_income", "finance_costs", "depreciation", "exceptional", "pbt", "tax", "pat"]
BANK_FIELDS = ["interest_earned", "interest_expended", "other_income", "operating_expenses", "pbt", "tax", "pat"]


def to_crore(value, unit: str | None):
    if value is None:
        return None
    return float(value) * UNIT_TO_CRORE.get((unit or "crore").strip().lower(), 1.0)


def change_pct(now, base):
    """(X_now - X_base)/|X_base| x 100; None (n.m.) when base is zero/negative or missing."""
    if now is None or base is None or base <= 0:
        return None
    return (now - base) / abs(base) * 100


def _delta(now, base):
    kind = None
    if now is not None and base is not None:
        if base < 0 <= now:
            kind = "turnaround to profit"
        elif base > 0 > now:
            kind = "swing to loss"
    return {"abs": None if now is None or base is None else now - base, "kind": kind}


def ebitda(c: dict):
    if c.get("pbt") is None:
        return None
    return c["pbt"] + (c.get("finance_costs") or 0) + (c.get("depreciation") or 0) - (c.get("other_income") or 0) + (c.get("exceptional") or 0)


def normalise(data: dict, bank: bool) -> dict:
    unit = data.get("unit")
    fields = BANK_FIELDS if bank else GENERAL_FIELDS
    cols = {}
    for col in COLS:
        raw = (data.get(col) or {})
        cols[col] = {f: to_crore(raw.get(f), unit) for f in fields}
    return cols


def metrics(cols: dict, bank: bool) -> dict:
    """Per column: the four headline values (+ margin for non-banks)."""
    out = {}
    for col, c in cols.items():
        if bank:
            nii = None if c["interest_earned"] is None or c["interest_expended"] is None else c["interest_earned"] - c["interest_expended"]
            ppop = None if nii is None or c["operating_expenses"] is None else nii + (c["other_income"] or 0) - c["operating_expenses"]
            out[col] = {"nii": nii, "ppop": ppop, "pbt": c["pbt"], "pat": c["pat"]}
        else:
            e = ebitda(c)
            out[col] = {"revenue": c["revenue"], "ebitda": e, "pbt": c["pbt"], "pat": c["pat"],
                        "margin": None if e is None or not c["revenue"] else e / c["revenue"] * 100}
    return out


def validate(cols: dict, m: dict, bank: bool) -> list[str]:
    """P-20: any failure means 'Needs review' and no numbers shown."""
    problems = []
    for col in COLS:
        c = cols[col]
        if c["pbt"] is None or c["pat"] is None or c["tax"] is None:
            problems.append(f"{col}: missing PBT/tax/PAT")
            continue
        if abs((c["pbt"] - c["tax"]) - c["pat"]) > max(0.01 * abs(c["pat"]), 0.5):
            problems.append(f"{col}: PBT - tax != PAT (within 1%)")
        if not bank:
            mg = m[col].get("margin")
            if mg is None:
                problems.append(f"{col}: EBITDA margin not computable")
            elif not -50 <= mg <= 80:
                problems.append(f"{col}: EBITDA margin {mg:.0f}% outside -50..80")
    if not problems and not bank and cols["now"]["revenue"] and cols["yoy"]["revenue"]:
        # column-order sanity: current quarter should not be wildly smaller than the year-ago quarter
        if cols["now"]["revenue"] < 0.1 * cols["yoy"]["revenue"]:
            problems.append("columns look reversed")
    return problems


def build_card(data: dict, bank: bool) -> dict:
    cols = normalise(data, bank)
    m = metrics(cols, bank)
    problems = validate(cols, m, bank)
    if problems:
        return {"kind": "results", "bank": bank, "needs_review": True, "problems": problems}
    keys = ["nii", "ppop", "pbt", "pat"] if bank else ["revenue", "ebitda", "pbt", "pat"]
    tiles = []
    for k in keys:
        now, qoq, yoy = (m[c][k] for c in COLS)
        tiles.append({"key": k, "value": now, "bars": [yoy, qoq, now],
                      "qoq_pct": change_pct(now, qoq), "yoy_pct": change_pct(now, yoy),
                      "qoq": _delta(now, qoq), "yoy": _delta(now, yoy)})
    margin_bps = None
    if not bank and m["now"]["margin"] is not None and m["yoy"]["margin"] is not None:
        margin_bps = (m["now"]["margin"] - m["yoy"]["margin"]) * 100
    card = {"kind": "results", "bank": bank, "needs_review": False, "unit": "crore", "tiles": tiles,
            "margin": None if bank else m["now"]["margin"], "margin_change_bps_yoy": margin_bps}
    card["sentence"] = sentence(card)
    return card


def _dir(p):
    return "n.m." if p is None else f"{'up' if p >= 0 else 'down'} {abs(p):.0f}%"


def sentence(card: dict) -> str:
    """Template sentence, no model: 'PAT up 23% YoY on 8% revenue growth; EBITDA margin up 120 bps.'"""
    t = {x["key"]: x for x in card["tiles"]}
    pat = t["pat"]
    s = f"PAT {_dir(pat['yoy_pct'])} YoY"
    if pat["yoy"]["kind"]:
        s = f"PAT {pat['yoy']['kind']} YoY"
    lead = t.get("revenue") or t.get("nii")
    if lead and lead["yoy_pct"] is not None:
        s += f" on {abs(lead['yoy_pct']):.0f}% {'revenue' if 'revenue' in t else 'NII'} {'growth' if lead['yoy_pct'] >= 0 else 'decline'}"
    if card.get("margin_change_bps_yoy") is not None:
        b = card["margin_change_bps_yoy"]
        s += f"; EBITDA margin {'up' if b >= 0 else 'down'} {abs(b):.0f} bps"
    return s + "."
