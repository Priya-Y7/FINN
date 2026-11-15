"""R-06: fiscal year runs April to March. Labels like 'Q2 FY26 (Jul-Sep 2025)'."""
from __future__ import annotations

MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fy(year: int, month: int) -> int:
    """Fiscal year (ending March) that a calendar month belongs to."""
    return year + 1 if month >= 4 else year


def quarter_no(month: int) -> int:
    return {6: 1, 9: 2, 12: 3, 3: 4}[month]


def quarter_end_for_call(year: int, month: int) -> tuple[int, int]:
    """The quarter a concall discusses: latest quarter end strictly before the call month."""
    m, y = month - 1, year
    if m == 0:                      # a January call: the previous month is December of last year
        m, y = 12, y - 1
    while m not in (3, 6, 9, 12):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return y, m


def quarter_label(year: int, month: int) -> str:
    start = month - 2
    return f"Q{quarter_no(month)} FY{fy(year, month) % 100:02d} ({MON[start - 1]}-{MON[month - 1]} {year})"


def quarter_code(year: int, month: int) -> str:
    return f"Q{quarter_no(month)}FY{fy(year, month) % 100:02d}"


def year_label(year: int, month: int = 3) -> str:
    return f"FY{fy(year, month) % 100:02d}"


def parse_period_end(text: str) -> tuple[int, int] | None:
    """'Mar 2026' -> (2026, 3)."""
    import re
    m = re.match(r"\s*([A-Za-z]{3})\w*\s+(\d{4})", text or "")
    if not m or m.group(1).title() not in MON:
        return None
    return int(m.group(2)), MON.index(m.group(1).title()) + 1
