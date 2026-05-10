"""Pure-logic helpers for plan_report.py.

Extracted from `plan_report.py` so mutation testing can target the
arithmetic / formatting / control-flow code without drowning in noise
from PDF coordinate / colour / font-size mutations in the rendering
helpers (`_styles`, `_header_band`, `_mini`, `_projection_chart`, …),
which aren't observable through unit tests.

Re-exported from `plan_report` for backwards compatibility with the
private `_fn` import names used by tests and within the rendering
module.
"""

from __future__ import annotations

import re


def fmt_money_inr(amount: float) -> str:
    """Indian notation with lakhs / crores."""
    if amount >= 1_00_00_000:
        return f"₹{amount / 1_00_00_000:.2f} Cr"
    if amount >= 1_00_000:
        return f"₹{amount / 1_00_000:.2f} L"
    return f"₹{amount:,.0f}"


def project_corpus(monthly_sip: float, horizon_years: int, annual_pct: float) -> float:
    """FV of a monthly SIP at a given annual % (compounded monthly).

    FV = P * [((1 + r)^n − 1) / r] * (1 + r)
    where P = monthly contribution, r = monthly rate, n = months.
    """
    if not monthly_sip or not horizon_years or annual_pct is None:
        return 0.0
    r = annual_pct / 100 / 12
    n = horizon_years * 12
    if r == 0:
        return monthly_sip * n
    return monthly_sip * ((pow(1 + r, n) - 1) / r) * (1 + r)


def projection_trace(
    monthly_sip: float, horizon_years: int, annual_pct: float
) -> list[tuple[float, float]]:
    """Per-year (year, corpus) pairs for the line chart."""
    trace: list[tuple[float, float]] = [(0.0, 0.0)]
    for year in range(1, horizon_years + 1):
        trace.append((float(year), project_corpus(monthly_sip, year, annual_pct)))
    return trace


def split_bullets(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        for prefix in ("- ", "* ", "+ ", "• "):
            if s.startswith(prefix):
                s = s[len(prefix) :]
                break
        s = re.sub(r"^\d+[.)]\s*", "", s)
        if s:
            out.append(s)
    return out or [text.strip()]
