"""R-07..R-14: promises from concalls, checked against numbers. Scoring is code, never the model."""
from __future__ import annotations

import difflib
import json
import re
from datetime import date

from .. import llm
from .periods import MON, quarter_label, year_label

# metric -> (keyword regex, unit, lower_is_better, kind of actual)
METRICS = {
    "revenue_growth": (r"revenue|sales|top ?line", "%", False),
    "op_margin": (r"ebitda margin|operating margin|\bmargins?\b", "%", False),
    "pat_growth": (r"\bpat\b|profit after tax|net profit|bottom ?line", "%", False),
    "borrowings": (r"\bdebt\b|borrowings?", "crore", True),
    "capex": (r"capex|capital expenditure", "crore", False),
}
METRIC_NAME = {"revenue_growth": "Revenue growth", "op_margin": "Operating margin", "pat_growth": "PAT growth",
               "borrowings": "Borrowings", "capex": "Capex"}
HORIZON = re.compile(r"\b(?:(Q[1-4])\s*)?(?:FY|fiscal(?:\s+year)?)\s?'?(\d{4}|\d{2})(?:\s*[-–/]\s*(\d{4}|\d{2}))?(?!\d)", re.I)
NUM = re.compile(r"(\d+(?:\.\d+)?)\s*(%|crore|cr\b)?", re.I)


def norm_horizon(text: str | None) -> str | None:
    """'FY24', 'FY2024', 'FY2024-25', 'Q3 FY25' -> 'FY24' / 'FY25' / 'Q3FY25' (a range means its end year)."""
    m = HORIZON.search(text or "")
    if not m:
        return None
    return f"{(m.group(1) or '').upper()}FY{int((m.group(3) or m.group(2))[-2:]):02d}"


def _numbers(sentence: str) -> list[float]:
    """Target numbers in a sentence, ignoring fiscal-year labels, calendar years and thousands commas."""
    t = HORIZON.sub(" ", sentence)
    t = re.sub(r"\bQ[1-4]\b", " ", t)
    t = re.sub(r"\b(?:19|20)\d{2}\b", " ", t)
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)
    return [float(n) for n, _ in NUM.findall(t)]


SENT = re.compile(r"(?<=[.!?])\s+")
SYSTEM = ("You extract forward-looking commitments from an Indian company's earnings call. Return JSON only: "
          '{"promises":[{"metric": one of %s, "target_low": number|null, "target_high": number|null, '
          '"direction": "up|down|null", "horizon": "FY26" or "Q3FY26" or null, "kind": "numeric|directional|qualitative", '
          '"quote": "verbatim sentence from the text", "source_id": "chunk id"}]}. Quote exactly; never invent numbers. '
          "Only use the provided text." % list(METRICS))


# ---------- extraction ----------
def heuristic_extract(chunks: list[dict]) -> list[dict]:
    """Rule-based extractor. Used as the offline fallback (mock mode) and tested like any code."""
    out = []
    for c in chunks:
        for s in SENT.split(c["text"].replace("\n", " ")):
            if not re.search(r"\b(expect|guid|target|aim|will|confident)\w*", s, re.I):
                continue
            metric = next((m for m, (rx, _, _) in METRICS.items() if re.search(rx, s, re.I)), None)
            if not metric:
                continue
            p = {"metric": metric, "quote": s.strip(), "source_id": c["id"], "horizon": None,
                 "target_low": None, "target_high": None, "direction": None, "kind": "qualitative"}
            p["horizon"] = norm_horizon(s)
            nums = _numbers(s)
            if nums:
                p["kind"], p["target_low"], p["target_high"] = "numeric", min(nums), max(nums)
            elif re.search(r"improv|expan|increas|grow|rise", s, re.I):
                p["kind"], p["direction"] = "directional", "up"
            elif re.search(r"reduc|lower|bring down|decreas", s, re.I):
                p["kind"], p["direction"] = "directional", "down"
            if p["kind"] != "qualitative":      # a bare mention with no number or direction is noise
                out.append(p)
    return out


def extract(chunks_by_call: dict[str, list[dict]]) -> list[dict]:
    """One transcript at a time; only cue-passing chunks are sent (R-07)."""
    from .retrieval import cue_chunks
    promises = []
    for call, chunks in chunks_by_call.items():
        sent = cue_chunks(chunks)
        if not sent:
            continue
        prompt = "\n\n".join(f"[{c['id']}]\n{c['text']}" for c in sent)[:24000]
        r = llm.complete("extract_promises", "cheap", SYSTEM, prompt, cache_parts=[call, [c["id"] for c in sent]], max_tokens=2000,
                         mock_response=json.dumps({"promises": heuristic_extract(sent)}))
        try:
            items = (llm.parse_json(r["text"]) or {}).get("promises", [])
        except Exception:  # noqa: BLE001
            items = []
        seen = set()
        for it in items:
            key = (it.get("metric"), it.get("kind"), it.get("target_low"), it.get("target_high"), it.get("direction"), it.get("horizon"))
            if key in seen:                 # the same guidance repeated within one call
                continue
            seen.add(key)
            it["call"] = call
            it["extracted_by"] = "rules (no API key)" if r["mock"] else "model"
            promises.append(it)
    return promises


# ---------- normalise (R-08) ----------
def normalise(p: dict) -> dict:
    q = (p.get("quote") or "").lower()
    p["derived"] = False
    if p.get("horizon"):
        p["horizon"] = norm_horizon(str(p["horizon"])) or p["horizon"]
    if p.get("metric") in METRICS and not p.get("horizon") and p.get("kind") != "qualitative":
        m = re.match(r"Q([1-4])FY(\d{2})$", p.get("call") or "")
        if m:       # guidance with no stated period: the coming year after a Q4 call, otherwise the current year
            yy = int(m.group(2)) + (1 if m.group(1) == "4" else 0)
            p["horizon"], p["horizon_inferred"] = f"FY{yy % 100:02d}", True
    if p.get("metric") not in METRICS:
        p["kind"] = "qualitative"
        return p
    if p.get("target_low") is None and p.get("target_high") is None:
        if "double-digit" in q or "double digit" in q:
            p.update(kind="numeric", target_low=10.0, target_high=None, derived=True)
        elif p.get("direction") in ("up", "down"):
            p["kind"] = "directional"
        else:
            p["kind"] = "qualitative"
    return p


# ---------- verify (R-09) ----------
def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%. ]", " ", (t or "").lower())).strip()


def quote_in_chunk(quote: str, text: str, thr: float = 0.9) -> bool:
    q, t = _norm(quote), _norm(text)
    if not q:
        return False
    if q in t:
        return True
    m = difflib.SequenceMatcher(None, t, q, autojunk=False).find_longest_match(0, len(t), 0, len(q))
    return m.size / len(q) >= thr


def verify(promises: list[dict], chunk_index: dict[str, dict]) -> tuple[list[dict], int]:
    kept, dropped = [], 0
    for p in promises:
        c = chunk_index.get(p.get("source_id"))
        ok = bool(c) and quote_in_chunk(p.get("quote", ""), c["text"])
        if ok and p.get("kind") == "numeric" and not p.get("derived"):
            for key in ("target_low", "target_high"):
                v = p.get(key)
                if v is None:
                    continue
                shown = f"{v:.2f}".rstrip("0").rstrip(".")
                if not re.search(rf"(?<![\d.]){re.escape(shown)}(?![\d])", re.sub(r"(?<=\d),(?=\d{3})", "", p["quote"])):
                    ok = False
        if ok:
            kept.append(p)
        else:
            dropped += 1
    return kept, dropped


# ---------- horizons and actuals (R-10) ----------
def horizon_end(h: str | None) -> tuple[int, int] | None:
    """'FY26' -> (2026, 3); 'Q2FY26' -> (2025, 9)."""
    m = re.match(r"^(Q[1-4])?\s*FY\s?'?(\d{2})$", (h or "").strip(), re.I)
    if not m:
        return None
    fy = 2000 + int(m.group(2))
    if not m.group(1):
        return fy, 3
    q = int(m.group(1)[1])
    return {1: (fy - 1, 6), 2: (fy - 1, 9), 3: (fy - 1, 12), 4: (fy, 3)}[q]


def horizon_label(h: str | None) -> str:
    e = horizon_end(h)
    if not e:
        return "no stated horizon"
    return quarter_label(*e) if (h or "").upper().startswith("Q") else year_label(*e)


def _val(df, key, metric):
    if df is None or df.empty or key not in df.index or metric not in df.columns:
        return None
    v = df.loc[key, metric]
    return None if v != v else float(v)


def actual_for(p: dict, annual, quarterly) -> tuple[float | None, str]:
    """Matching actual from structured financials, or (None, reason). Never guesses."""
    e = horizon_end(p.get("horizon"))
    if not e:
        return None, "no stated horizon"
    key = f"{e[0]}-{e[1]:02d}"
    is_q = p["horizon"].upper().startswith("Q")
    df = quarterly if is_q else annual
    m = p["metric"]
    if df is None or df.empty or key not in df.index:
        return None, "period not in financials"
    idx = list(df.index)
    prev_key = None
    if m in ("revenue_growth", "pat_growth"):
        back = 4 if is_q else 1       # quarter vs same quarter last year; year vs prior year
        i = idx.index(key)
        if i - back < 0:
            return None, "no comparison period"
        prev_key = idx[i - back]
        col = "sales" if m == "revenue_growth" else "pat"
        a, b = _val(df, key, col), _val(df, prev_key, col)
        if a is None or b is None or b <= 0:
            return None, "comparison base missing or not positive"
        return (a / b - 1) * 100, f"{col} {a:.0f} vs {b:.0f} crore"
    if m == "op_margin":
        a, s = _val(df, key, "operating_profit"), _val(df, key, "sales")
        return (None, "margin inputs missing") if a is None or not s else (a / s * 100, f"operating profit {a:.0f} / sales {s:.0f}")
    if m == "borrowings":
        v = _val(df, key, "borrowings")
        return (v, "borrowings at period end") if v is not None else (None, "borrowings missing")
    if m == "capex":
        v = _val(df, key, "capex")
        return (abs(v), "capex as reported") if v is not None else (None, "capex missing")
    return None, "unsupported metric"


def prior_for(p: dict, annual, quarterly) -> float | None:
    """For directional promises: the value in the preceding comparable period."""
    e = horizon_end(p.get("horizon"))
    if not e:
        return None
    is_q = p["horizon"].upper().startswith("Q")
    df = quarterly if is_q else annual
    if df is None or df.empty:
        return None
    idx = list(df.index)
    key = f"{e[0]}-{e[1]:02d}"
    if key not in idx or idx.index(key) == 0:
        return None
    pk = idx[idx.index(key) - 1]
    if p["metric"] == "op_margin":
        a, s = _val(df, pk, "operating_profit"), _val(df, pk, "sales")
        return None if a is None or not s else a / s * 100
    return _val(df, pk, {"borrowings": "borrowings", "capex": "capex"}.get(p["metric"], "sales"))


# ---------- scoring (R-11, R-12) ----------
def score(p: dict, annual, quarterly, today: date | None = None) -> dict:
    today = today or date.today()
    out = {**p, "status": "cant_verify", "actual": None, "achievement": None, "gap_bps": None, "note": ""}
    e = horizon_end(p.get("horizon"))
    if p.get("kind") == "qualitative" or p.get("metric") not in METRICS:
        out["note"] = "Qualitative statement: no comparable number"
        return out
    if not e:
        out["note"] = "No stated horizon"
        return out
    end_day = date(e[0] + (1 if e[1] == 12 else 0), (e[1] % 12) + 1, 1)   # first day after the period ends
    if today < end_day:
        out.update(status="not_due", note="Horizon not ended")
        return out
    actual, note = actual_for(p, annual, quarterly)
    if p.get("horizon_inferred") and actual is not None:
        note += " (period not stated on the call; assumed the fiscal year it was guiding)"
    if actual is None:
        out["note"] = f"Can't verify: {note}"
        return out
    out["actual"], out["note"] = actual, note
    lower_better = METRICS[p["metric"]][2]
    if p["kind"] == "directional":
        prior = prior_for(p, annual, quarterly)
        if prior is None:
            out.update(status="cant_verify", note="No prior period to compare")
            return out
        improved = actual < prior if p.get("direction") == "down" or lower_better else actual > prior
        out.update(status="delivered" if improved else "missed", note=f"{actual:.1f} vs {prior:.1f} in the prior period")
        return out
    lo, hi = p.get("target_low"), p.get("target_high")
    target = lo if lo is not None else hi
    if target is None or target <= 0 or actual <= 0:
        out["note"] = "Can't verify: target or actual not positive"
        return out
    ratio = target / actual if lower_better else actual / target
    in_range = lo is not None and hi is not None and lo <= actual <= hi
    out["achievement"] = ratio
    if METRICS[p["metric"]][1] == "%":
        out["gap_bps"] = (actual - target) * 100
    out["status"] = "delivered" if (ratio >= 1 or in_range) else "partly" if ratio >= 0.9 else "missed"
    return out


def delivery_rate(scored: list[dict]) -> dict:
    c = {s: sum(1 for p in scored if p["status"] == s) for s in ("delivered", "partly", "missed", "not_due", "cant_verify")}
    n = c["delivered"] + c["partly"] + c["missed"]
    return {"rate": None if n == 0 else (c["delivered"] + 0.5 * c["partly"]) / n, "based_on": n, **c}


# ---------- flags (R-13) ----------
GLOW = re.compile(r"margins? (are |is |will )?(improv|expand)|strong demand|robust demand|demand (remains|is) (strong|robust)", re.I)


def flags(promises: list[dict], chunks_by_call: dict[str, list[dict]], quarterly) -> list[dict]:
    out = []
    calls = sorted(chunks_by_call, key=lambda c: (c[-2:], c[:2]))
    # narrative vs numbers: upbeat language on two calls in a row while margin and growth fell in both quarters
    if len(calls) >= 2 and quarterly is not None and not quarterly.empty and len(quarterly) >= 6:
        last2 = calls[-2:]
        if all(any(GLOW.search(c["text"]) for c in chunks_by_call[k]) for k in last2):
            q = quarterly.copy()
            q["m"] = q["operating_profit"] / q["sales"]
            m, s = list(q["m"].tail(3)), list(q["sales"].tail(3))
            if m[2] < m[1] < m[0] and s[2] < s[1] < s[0]:
                out.append({"kind": "narrative_vs_numbers", "text": "Management sounded upbeat on margins or demand on the last two calls, but operating margin and sales fell in both recent quarters."})
    # guidance softened between calls
    by_metric: dict[str, list[dict]] = {}
    for p in promises:
        if p.get("kind") == "numeric" and p.get("horizon"):
            by_metric.setdefault(p["metric"], []).append(p)
    for m, ps in by_metric.items():
        ps.sort(key=lambda p: (p["call"][-2:], p["call"][:2]))
        for a, b in zip(ps, ps[1:]):
            a_end, b_end, b_call = horizon_end(a["horizon"]), horizon_end(b["horizon"]), horizon_end(b["call"])
            if a["horizon"] == b["horizon"] and (b.get("target_low") or 0) < (a.get("target_low") or 0) and not METRICS[m][2]:
                out.append({"kind": "softened", "text": f"{METRIC_NAME[m]} target for {horizon_label(a['horizon'])} was lowered from {a['target_low']:g} to {b['target_low']:g} between the {a['call']} and {b['call']} calls.", "ids": [a["source_id"], b["source_id"]]})
            elif a_end and b_end and b_call and b_end > a_end > b_call:
                # the earlier horizon was still open when the later call was held, and the goalpost moved out
                out.append({"kind": "softened", "text": f"{METRIC_NAME[m]} horizon moved out from {horizon_label(a['horizon'])} to {horizon_label(b['horizon'])}.", "ids": [a["source_id"], b["source_id"]]})
    if len(calls) >= 2:
        latest = calls[-1]
        l_end = horizon_end(latest)
        for m, ps in by_metric.items():
            earlier = [p for p in ps if p["call"] != latest]
            if earlier and all(p["call"] != latest for p in ps) and horizon_end(earlier[-1]["horizon"]) and l_end \
                    and horizon_end(earlier[-1]["horizon"]) > l_end:
                out.append({"kind": "dropped", "text": f"{METRIC_NAME[m]} target for {horizon_label(earlier[-1]['horizon'])} was not repeated on the {latest} call.", "ids": [earlier[-1]["source_id"]]})
    return out


# ---------- verdict (R-14) ----------
def verdict(scored: list[dict], flg: list[dict], dr: dict) -> dict:
    """Three lines. Template in code; the strong model may reword it but sees only the scored list."""
    if dr["based_on"] == 0:
        base = ["No promises with a finished horizon could be checked yet."]
    else:
        by_m: dict[str, list[str]] = {}
        for p in scored:
            if p["status"] in ("delivered", "partly", "missed"):
                by_m.setdefault(p["metric"], []).append(p["status"])
        parts = []
        for m, sts in by_m.items():
            d, x = sts.count("delivered"), sts.count("missed")
            parts.append(f"{'delivered' if x == 0 else 'missed' if d == 0 else 'mixed'} on {METRIC_NAME[m].lower()}"
                         + (f" ({'twice' if x == 2 else str(x) + 'x'})" if x > 1 and d == 0 else ""))
        base = [f"Delivery rate {dr['rate'] * 100:.0f}% across {dr['based_on']} checkable promises "
                f"({dr['delivered']} delivered, {dr['partly']} partly, {dr['missed']} missed).",
                (parts[0].capitalize() + "".join(f"; {x}" for x in parts[1:]) + ".") if parts else ""]
    if flg:
        base.append(flg[0]["text"])
    lines = [l for l in base if l][:3]
    payload = {"promises": [{k: p.get(k) for k in ("metric", "horizon", "status", "target_low", "target_high", "actual")} for p in scored], "flags": [f["text"] for f in flg], "delivery": dr}
    r = llm.complete("verdict", "strong", "Write exactly three short lines summarising this promise scorecard for an investor. "
                     "Use only the JSON provided; add no facts. Return the three lines separated by newlines.",
                     json.dumps(payload, sort_keys=True, default=str), cache_parts=[json.dumps(payload, sort_keys=True, default=str)],
                     max_tokens=300, mock_response="\n".join(lines))
    text = [l.strip() for l in r["text"].splitlines() if l.strip()][:3] or lines
    return {"lines": text, "by_model": not r["mock"]}
