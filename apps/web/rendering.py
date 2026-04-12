"""Rendering helpers for the FinAdvisor wizard web app.

Provides INR formatting, markdown-to-HTML conversion, corpus projection math,
and Chart.js data helpers.
"""

from __future__ import annotations

import html
import math

import markdown as _markdown_lib


# ---------------------------------------------------------------------------
# INR formatting
# ---------------------------------------------------------------------------

_CRORE = 10_000_000
_LAKH = 100_000


def format_inr(amount: float) -> str:
    """Format a rupee amount in lakhs/crores notation.

    Examples:
        format_inr(25_000_000)  -> "₹2.50 Cr"
        format_inr(550_000)     -> "₹5.50 L"
        format_inr(45_000)      -> "₹45,000"
        format_inr(0)           -> "₹0"
    """
    if amount == 0:
        return "₹0"
    if amount >= _CRORE:
        return f"₹{amount / _CRORE:.2f} Cr"
    if amount >= _LAKH:
        return f"₹{amount / _LAKH:.2f} L"
    return f"₹{int(amount):,}"


# ---------------------------------------------------------------------------
# Markdown to safe HTML
# ---------------------------------------------------------------------------

def render_markdown(text: str) -> str:
    """Convert markdown to safe HTML.

    Empty string returns empty string. HTML special characters are escaped
    before processing so user-supplied text cannot inject raw tags.
    Uses the ``sane_lists`` extension.
    """
    if not text:
        return ""
    # Escape any raw HTML in the source so it cannot be injected as-is.
    # We do this by converting the markdown with safe_mode-equivalent approach:
    # html.escape the input first, then process headings/bold/lists normally.
    # However, standard markdown already handles this via its HTML sanitiser.
    # We use the `escape` extra that prevents raw HTML passthrough.
    escaped = html.escape(text, quote=False)
    result = _markdown_lib.markdown(escaped, extensions=["sane_lists"])
    return result


# ---------------------------------------------------------------------------
# Corpus projection math
# ---------------------------------------------------------------------------

def compute_corpus(monthly_sip: float, years: int, cagr_pct: float) -> float:
    """Future value of a monthly SIP at a given CAGR.

    Returns 0.0 if any input is <= 0.

    Formula: sip * (((1+r)^n - 1) / r) * (1+r)
    where r = cagr_pct / 100 / 12, n = years * 12.
    """
    if monthly_sip <= 0 or years <= 0 or cagr_pct <= 0:
        return 0.0
    r = cagr_pct / 100.0 / 12.0
    n = years * 12
    future_value = monthly_sip * (((1 + r) ** n - 1) / r) * (1 + r)
    return future_value


def inflation_adjusted(future_value: float, years: int, inflation_pct: float = 6.0) -> float:
    """Discount a future value to today's terms using inflation.

    If years <= 0, returns future_value unchanged.
    Formula: future_value / (1 + inflation_pct/100)^years
    """
    if years <= 0:
        return future_value
    divisor = (1 + inflation_pct / 100.0) ** years
    return future_value / divisor


# ---------------------------------------------------------------------------
# Chart.js data helpers
# ---------------------------------------------------------------------------

_DONUT_SEGMENTS = [
    ("Equity", "#4f46e5"),
    ("Debt", "#0891b2"),
    ("Gold", "#d97706"),
    ("Other", "#6b7280"),
]


def chart_data_donut(
    equity: float,
    debt: float,
    gold: float,
    other: float,
) -> dict:
    """Build Chart.js donut chart data for asset allocation.

    Only includes segments with value > 0.

    Returns:
        {"labels": [...], "values": [...], "colors": [...]}
    """
    raw = [equity, debt, gold, other]
    labels = []
    values = []
    colors = []
    for (name, color), value in zip(_DONUT_SEGMENTS, raw):
        if value > 0:
            labels.append(name)
            values.append(value)
            colors.append(color)
    return {"labels": labels, "values": values, "colors": colors}


_SCENARIO_DEFS = [
    ("Bear", "#ef4444"),
    ("Base", "#f59e0b"),
    ("Bull", "#22c55e"),
]


def chart_data_corpus(
    monthly_sip: float,
    years: int,
    bear: float,
    base: float,
    bull: float,
) -> dict:
    """Build Chart.js data for corpus growth scenarios.

    Only includes scenarios where cagr > 0.

    Returns:
        {
            "scenarios": [
                {
                    "label": str,
                    "cagr": float,
                    "future_value": float,
                    "present_value": float,
                    "future_value_fmt": str,
                    "present_value_fmt": str,
                    "color": str,
                },
                ...
            ],
            "sip_fmt": str,
            "years": int,
        }
    """
    cagr_values = [bear, base, bull]
    scenarios = []
    for (label, color), cagr in zip(_SCENARIO_DEFS, cagr_values):
        if cagr <= 0:
            continue
        fv = compute_corpus(monthly_sip, years, cagr)
        pv = inflation_adjusted(fv, years)
        scenarios.append(
            {
                "label": label,
                "cagr": cagr,
                "future_value": fv,
                "present_value": pv,
                "future_value_fmt": format_inr(fv),
                "present_value_fmt": format_inr(pv),
                "color": color,
            }
        )
    return {
        "scenarios": scenarios,
        "sip_fmt": format_inr(monthly_sip),
        "years": years,
    }
