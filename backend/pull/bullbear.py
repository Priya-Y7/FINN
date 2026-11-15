"""R-20/R-21: three bull and three bear points from company documents only; every point must cite packet ids."""
from __future__ import annotations

import json

from .. import llm
from .retrieval import Index

TOPICS = ["outlook growth demand", "risks challenges headwinds", "capex capacity expansion investment", "competition market share pricing", "debt borrowings leverage"]
SYSTEM = ("You write a balanced case from company documents ONLY. Use only the PACKET. No outside knowledge, no predictions, no price targets, "
          "no advice. Return JSON only: {\"bull\":[{\"text\":\"one sentence\",\"ids\":[\"id\",...]} x3],\"bear\":[... x3]}. "
          "Every point must cite one or more ids that appear in the packet.")


def passages(index: Index, per_topic: int = 3, cap: int = 12) -> list[dict]:
    seen, out = set(), []
    for t in TOPICS:
        for c in index.search(t, k=per_topic):
            if c["id"] not in seen:
                seen.add(c["id"])
                out.append(c)
    return out[:cap]


def validate(data: dict, allowed: set[str]) -> list[str]:
    """Returns problems; empty list means the answer is acceptable."""
    problems = []
    for side in ("bull", "bear"):
        pts = data.get(side) or []
        if len(pts) != 3:
            problems.append(f"{side}: expected exactly 3 points, got {len(pts)}")
        for p in pts:
            ids = p.get("ids") or []
            if not p.get("text") or not ids:
                problems.append(f"{side}: point without text or citation")
            elif any(i not in allowed for i in ids):
                problems.append(f"{side}: cites an id not in the packet")
    return problems


def template(snapshot: dict, scorecard: dict, ps: list[dict]) -> dict:
    """Deterministic fallback (no API key): states facts already computed in code, each with its evidence id."""
    bull, bear = [], []
    for c in snapshot.get("callouts", []):
        (bull if c["kind"] == "growing" else bear).append({"text": c["text"], "ids": ["FIN"]})
    dr = scorecard.get("delivery", {})
    if dr.get("rate") is not None:
        (bull if dr["rate"] >= 0.6 else bear).append({"text": f"Management delivered on {dr['delivered']} of {dr['based_on']} checkable promises.", "ids": [p["source_id"] for p in scorecard["promises"] if p["status"] != "not_due"][:2] or ["FIN"]})
    for f in scorecard.get("flags", []):
        bear.append({"text": f["text"], "ids": f.get("ids") or ["FIN"]})
    for p in ps:
        txt = p["text"].replace("\n", " ")
        first = txt.split(". ")[0][:220]
        side = bear if ("risk" in p["section"].lower() or "risk" in txt.lower()[:200]) else bull
        side.append({"text": first.rstrip(".") + ".", "ids": [p["id"]]})
    last = snapshot.get("tiles", [{}])[0]
    while len(bull) < 3:
        bull.append({"text": "Not enough supportive evidence found in the documents.", "ids": ["FIN"]})
    while len(bear) < 3:
        bear.append({"text": "Not enough cautionary evidence found in the documents.", "ids": ["FIN"]})
    return {"bull": bull[:3], "bear": bear[:3]}


def generate(snapshot: dict, scorecard: dict, index: Index) -> dict:
    ps = passages(index)
    allowed = {"FIN"} | {p["id"] for p in ps} | {p["source_id"] for p in scorecard.get("promises", []) if p.get("source_id")} \
        | {i for f in scorecard.get("flags", []) for i in f.get("ids", [])}
    packet = {"snapshot": {k: snapshot.get(k) for k in ("tiles", "callouts")}, "scorecard": {"delivery": scorecard.get("delivery"), "flags": [{"text": f["text"], "ids": f.get("ids", [])} for f in scorecard.get("flags", [])],
              "promises": [{k: p.get(k) for k in ("metric", "horizon", "status", "target_low", "actual", "source_id")} for p in scorecard.get("promises", [])]},
              "passages": [{"id": p["id"], "text": p["text"][:900]} for p in ps]}
    prompt = "PACKET (ids you may cite: FIN, " + ", ".join(sorted(allowed - {"FIN"})) + ")\n" + json.dumps(packet, default=str)
    mock = json.dumps(template(snapshot, scorecard, ps))
    key = json.dumps(packet, sort_keys=True, default=str)
    data, problems, by_model = {}, ["not run"], False
    for attempt in range(2):                      # re-ask once on a guard failure
        extra = "" if attempt == 0 else "\nYour previous answer failed: " + "; ".join(problems) + ". Fix it."
        r = llm.complete("bullbear", "strong", SYSTEM, prompt + extra, cache_parts=[key, attempt], max_tokens=1200, mock_response=mock)
        try:
            data = llm.parse_json(r["text"]) or {}
        except Exception:  # noqa: BLE001
            data = {}
        problems = validate(data, allowed)
        by_model = not r["mock"]
        if not problems:
            break
    if problems:
        return {"available": False, "reason": "; ".join(problems)}
    return {"available": True, "bull": data["bull"], "bear": data["bear"], "by_model": by_model,
            "sources": {p["id"]: {"label": p["id"]} for p in ps}, "footer": "A case for each side from company documents only. Not advice."}
