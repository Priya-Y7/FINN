"""P-01..P-04, P-37: windowed digest. No model at read time."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
TIER_NAME = {1: "need you", 2: "worth knowing", 3: "routine hidden"}


def _bounds(frm: str | None, to: str | None, days: int = 1) -> tuple[str, str]:
    """Window on filing timestamp. Date-only values are read as IST days."""
    def parse(v, end):
        if len(v) == 10:
            d = datetime.strptime(v, "%Y-%m-%d").replace(tzinfo=IST)
            return (d + timedelta(days=1) if end else d).astimezone(timezone.utc)
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)
    t = parse(to, True) if to else datetime.now(timezone.utc)
    f = parse(frm, False) if frm else t - timedelta(days=days)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return f.strftime(fmt), t.strftime(fmt)


def _fetch(conn, f: str, t: str) -> list[dict]:
    rows = conn.execute(
        """SELECT a.*, c.name, c.sector, c.in_portfolio,
                  (SELECT ret_pct FROM prices p WHERE p.ticker=a.ticker ORDER BY date DESC LIMIT 1) AS day_change
           FROM announcements a JOIN companies c ON c.ticker=a.ticker
           WHERE a.ts >= ? AND a.ts < ? AND a.tier IS NOT NULL ORDER BY a.tier, a.score DESC, a.ts DESC""", (f, t)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        enr = json.loads(d.pop("enrichment_json") or "{}")
        d["card"], d["breakdown"], d["alt_links"] = enr.get("card"), enr.get("breakdown"), enr.get("alt_links", [])
        out.append(d)
    return out


def summary_line(counts: dict) -> str:
    if not any(counts.values()):
        return "Nothing filed in this window."
    return ", ".join(f"{counts[t]} {TIER_NAME[t]}" for t in (1, 2, 3))


def build(conn, frm: str | None = None, to: str | None = None, days: int = 1, only_portfolio: bool = True) -> dict:
    f, t = _bounds(frm, to, days)
    items = _fetch(conn, f, t)
    notice = None
    if not items and not frm:     # P-03: fall back to the last day that has filings
        last = conn.execute("SELECT MAX(ts) m FROM announcements WHERE tier IS NOT NULL").fetchone()["m"]
        if last:
            day = datetime.fromisoformat(last.replace("Z", "+00:00")).astimezone(IST).strftime("%Y-%m-%d")
            f, t = _bounds(day, day)
            items = _fetch(conn, f, t)
            notice = f"No filings in this window. Showing the last day with filings ({day})."
    if only_portfolio:
        items = [i for i in items if i["in_portfolio"]]
    counts = {1: 0, 2: 0, 3: 0}
    for i in items:
        counts[i["tier"]] += 1
    for i in items:
        if i["tier"] == 3:   # routine: title only
            i["card"] = None
    return {"from": f, "to": t, "notice": notice, "counts": counts, "summary": summary_line(counts),
            "tiers": {"act_now": [i for i in items if i["tier"] == 1], "worth_knowing": [i for i in items if i["tier"] == 2],
                      "routine": [i for i in items if i["tier"] == 3]},
            "briefing": briefing(items)}


def briefing(items: list[dict]) -> str:
    """P-37: built by rules from the digest."""
    t1 = [i for i in items if i["tier"] == 1]
    n2 = sum(1 for i in items if i["tier"] == 2)
    if not t1 and not n2:
        return "Nothing material since your last visit."
    head = f"{len(t1)} need you, {n2} worth knowing."
    lines = []
    for i in t1[:2]:
        what = i.get("summary") or (i["category"] or "filing").replace("_", " ")
        lines.append(f"{i['ticker']}: {what}")
    return " ".join([head] + [l.rstrip(".") + "." for l in lines])
