"""P-05: rules first; only unplaceable filings go to the cheap model."""
from __future__ import annotations

import re

CATEGORIES = ["results", "m&a", "fund_raise", "management_change", "litigation", "insider_trading", "earnings_call",
              "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex", "press_release",
              "postal_ballot", "agm_egm", "pledging", "unclassified"]

# Order matters: first match wins. Patterns run on "category_text + title", lower-cased.
RULES: list[tuple[str, str]] = [
    ("results", r"financial results|unaudited.*results|audited.*results|quarterly results|outcome of board meeting.*results"),
    ("insider_trading", r"insider trading|sebi \(pit\)|regulation 7\(|trading window|disclosure under regulation 29|acquisition.*shares.*promoter"),
    ("pledging", r"pledge|encumbrance|invocation"),
    ("credit_rating", r"credit rating|rating (action|reaffirm|upgrade|downgrade|assigned|revised)|crisil|icra|care ratings|india ratings"),
    ("management_change", r"appointment of|resignation|cessation|change in (key )?management|change in director|retire|re-?designation|senior management|chief (executive|financial)|company secretary|auditor"),
    ("m&a", r"acquisition|merger|amalgamation|demerger|scheme of arrangement|takeover|stake (sale|purchase)|joint venture|divestment"),
    ("fund_raise", r"fund ?raising|qip|preferential (issue|allotment)|rights issue|ncd|debentures|raising of funds|fpo|ecb|allotment of"),
    ("litigation", r"litigation|court|tribunal|penalty|show cause|notice from|order passed|arbitration|sebi order|fraud"),
    ("bonus_split", r"bonus|stock split|sub-?division|split of"),
    ("dividend", r"dividend|record date.*dividend"),
    ("capex", r"capex|capital expenditure|capacity|expansion|new plant|commissioning|commercial production"),
    ("earnings_call", r"earnings call|conference call|con call|transcript|audio recording"),
    ("investor_meetings", r"analyst|institutional investor|investor meet|investor presentation|schedule of"),
    ("postal_ballot", r"postal ballot|e-?voting"),
    ("agm_egm", r"annual general meeting|extra-?ordinary general|\bagm\b|\begm\b|book closure"),
    ("press_release", r"press release|order (win|received)|receipt of order|bags? order|new order|contract|awarded|letter of award|media release"),
]
_COMPILED = [(c, re.compile(p)) for c, p in RULES]


def rule_classify(category_text: str | None, title: str | None) -> str | None:
    text = f"{category_text or ''} {title or ''}".lower()
    for cat, rx in _COMPILED:
        if rx.search(text):
            return cat
    return None


def severity(category: str, text: str) -> tuple[int, str]:
    """M_sev: (points, reason). Only categories that carry severity are scored."""
    t = (text or "").lower()
    if category == "management_change":
        top = re.search(r"\b(ceo|cfo|chief executive|chief financial|managing director|\bmd\b|chairman|chairperson|auditor)\b", t)
        pts, why = (80, "top-role change") if top else (50, "other director/KMP") if re.search(r"director|kmp|key managerial|company secretary", t) else (0, "")
        if re.search(r"resign|cessation|step(s|ping)? down|demise", t) and not re.search(r"successor|in place of|replac", t):
            pts, why = pts + 10, (why + "; no successor named").strip("; ")
        return pts, why
    if category == "credit_rating":
        if re.search(r"downgrad", t):
            return 85, "downgrade"
        if re.search(r"upgrad", t):
            return 70, "upgrade"
        if re.search(r"reaffirm", t):
            return 40, "reaffirmed"
    return 0, ""


LLM_SYSTEM = ("Classify an Indian stock-exchange filing. Return JSON only: "
              '{"category": one of %s, "severity": 0-100, "one_line": "<=20 words"}' % CATEGORIES)


def llm_classify(title: str, category_text: str | None, ticker: str) -> dict:
    from .. import llm
    r = llm.complete("classify", "cheap", LLM_SYSTEM, f"{ticker}\nExchange category: {category_text}\nSubject: {title}",
                     cache_parts=[ticker, title], max_tokens=200,
                     mock_response='{"category": "unclassified", "severity": 0, "one_line": ""}')
    try:
        data = llm.parse_json(r["text"]) or {}
    except Exception:  # noqa: BLE001
        data = {}
    cat = data.get("category")
    return {"category": cat if cat in CATEGORIES else "unclassified", "one_line": data.get("one_line") or ""}


def classify(ticker: str, category_text: str | None, title: str, use_llm: bool = True) -> tuple[str, str]:
    """Returns (category, method) with method in rules|llm|none."""
    cat = rule_classify(category_text, title)
    if cat:
        return cat, "rules"
    if use_llm:
        c = llm_classify(title, category_text, ticker)["category"]
        return c, "llm"
    return "unclassified", "none"
