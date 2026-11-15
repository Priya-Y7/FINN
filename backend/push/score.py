"""P-06 / P-07: S = B_cat + M_sev + M_mkt + M_hold, with a breakdown for the info popover."""
from __future__ import annotations

from .. import config
from .classify import severity

BASE = {"results": 90, "m&a": 85, "management_change": 80, "litigation": 75, "fund_raise": 70, "credit_rating": 65,
        "pledging": 65, "capex": 55, "dividend": 50, "bonus_split": 50, "insider_trading": 45, "press_release": 40,
        "earnings_call": 35, "investor_meetings": 15, "postal_ballot": 10, "agm_egm": 10, "unclassified": 5}

FORMULA = "S = base(category) + severity + market reaction + position size"


def market_points(rets: list[tuple[float | None, float | None]]) -> tuple[int, str]:
    """rets: [(ret_pct, vol_ratio)] for filing day and next trading day. +10 for |move|>=3%, +10 more for volume>=2x."""
    pts, why = 0, []
    if any(r is not None and abs(r) >= 3 for r, _ in rets):
        pts += 10
        why.append("move >= 3%")
        if any(v is not None and v >= 2 for _, v in rets):
            pts += 10
            why.append("volume >= 2x")
    return pts, ", ".join(why)


def holding_points(weight: float | None, max_weight: float) -> int:
    if not weight or not max_weight:
        return 0
    return round(10 * weight / max_weight)


def tier_for(score: float) -> int:
    t = config.settings()["tiers"]
    return 1 if score >= t["act_now_min"] else 2 if score >= t["worth_knowing_min"] else 3


def score(category: str, text: str, rets, weight: float | None, max_weight: float) -> dict:
    base = BASE.get(category, 5)
    sev, sev_why = severity(category, text)
    mkt, mkt_why = market_points(rets)
    hold = holding_points(weight, max_weight)
    total = base + sev + mkt + hold
    return {"score": total, "tier": tier_for(total),
            "breakdown": {"base": base, "severity": sev, "severity_reason": sev_why, "market": mkt,
                          "market_reason": mkt_why, "position": hold, "formula": FORMULA}}
