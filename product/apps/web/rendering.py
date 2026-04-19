"""Rendering helpers for the Benji wizard web app.

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
# Fund name compression — strips noise words for small-screen display.
# Full name should still be shown as a tooltip via the title attribute.
# ---------------------------------------------------------------------------

# Tokens that add no information once the user knows the category + AMC.
# Matched case-insensitively as whole words; order doesn't matter.
_FUND_NAME_NOISE = (
    "Direct", "Regular", "Reg", "Plan",
    "Growth", "IDCW", "Dividend",
    "Option", "Scheme", "Fund",
    "Payout", "Reinvestment",
    "-", "–",  # stray separators left behind after stripping
)


def short_fund_name(name: str, max_len: int = 32) -> str:
    """Return a compact version of a fund name suitable for narrow columns.

    Strategy:
      1. Drop common noise words (Direct, Growth, Fund, Plan, Regular, IDCW…).
      2. Collapse any leftover whitespace.
      3. If still too long, truncate with an ellipsis.

    Examples:
        "HDFC Index Fund - NIFTY 50 Plan - Direct Plan - Growth Option"
            -> "HDFC Index NIFTY 50"
        "Mirae Asset Large Cap Fund Direct Growth"
            -> "Mirae Asset Large Cap"
    """
    if not name:
        return ""
    tokens = name.split()
    noise_lower = {w.lower() for w in _FUND_NAME_NOISE}
    kept = [t for t in tokens if t.lower().strip(".,-") not in noise_lower]
    result = " ".join(kept).strip()
    # Collapse doubled separators left behind (e.g. "NIFTY 50  -  Plan")
    while "  " in result:
        result = result.replace("  ", " ")
    for sep in (" - ", " – "):
        while sep.strip() + " " in result or " " + sep.strip() in result:
            result = result.replace(sep, " ").strip()
    if len(result) > max_len:
        result = result[: max_len - 1].rstrip() + "…"
    return result or name  # fall back to full name if stripping emptied it


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


_SUB_COLORS = {
    # Equity shades (indigo family)
    "Large Cap": "#6366f1", "Mid Cap": "#818cf8", "Small Cap": "#a5b4fc",
    "Flexi Cap": "#7c3aed", "Multi Cap": "#8b5cf6", "ELSS": "#6d28d9",
    "Index": "#4f46e5", "Sectoral": "#4338ca", "International": "#3730a3",
    # Debt shades (cyan family)
    "Short Duration": "#06b6d4", "Corporate Bond": "#22d3ee",
    "Gilt": "#0e7490", "Liquid": "#67e8f9", "Dynamic Bond": "#0891b2",
    # Gold
    "Gold": "#d97706", "Gold ETF": "#f59e0b",
    # Other
    "Other": "#6b7280",
}


def chart_data_donut(
    equity: float,
    debt: float,
    gold: float,
    other: float,
    equity_sub: dict[str, float] | None = None,
    debt_sub: dict[str, float] | None = None,
) -> dict:
    """Build nested donut chart data for asset allocation.

    Returns:
        {
            "inner": {"labels": [...], "values": [...], "colors": [...]},  # asset classes
            "outer": {"labels": [...], "values": [...], "colors": [...]},  # sub-categories
        }

    If no sub-categories are provided, outer ring mirrors inner ring.
    """
    # Inner ring: asset classes
    inner_labels, inner_values, inner_colors = [], [], []
    for (name, color), value in zip(_DONUT_SEGMENTS, [equity, debt, gold, other]):
        if value > 0:
            inner_labels.append(name)
            inner_values.append(round(value, 1))
            inner_colors.append(color)

    # Outer ring: sub-categories (or mirror inner if none)
    outer_labels, outer_values, outer_colors = [], [], []
    has_subs = (equity_sub and sum(equity_sub.values()) > 0) or (debt_sub and sum(debt_sub.values()) > 0)

    if has_subs:
        # Equity subs
        if equity > 0:
            if equity_sub and sum(equity_sub.values()) > 0:
                for cat, pct in equity_sub.items():
                    if pct > 0:
                        outer_labels.append(cat)
                        outer_values.append(round(pct, 1))
                        outer_colors.append(_SUB_COLORS.get(cat, "#4f46e5"))
                # If subs don't add up to equity_pct, add remainder
                sub_total = sum(equity_sub.values())
                if sub_total < equity - 0.5:
                    outer_labels.append("Other Equity")
                    outer_values.append(round(equity - sub_total, 1))
                    outer_colors.append("#c7d2fe")
            else:
                outer_labels.append("Equity")
                outer_values.append(round(equity, 1))
                outer_colors.append("#4f46e5")

        # Debt subs
        if debt > 0:
            if debt_sub and sum(debt_sub.values()) > 0:
                for cat, pct in debt_sub.items():
                    if pct > 0:
                        outer_labels.append(cat)
                        outer_values.append(round(pct, 1))
                        outer_colors.append(_SUB_COLORS.get(cat, "#0891b2"))
                sub_total = sum(debt_sub.values())
                if sub_total < debt - 0.5:
                    outer_labels.append("Other Debt")
                    outer_values.append(round(debt - sub_total, 1))
                    outer_colors.append("#a5f3fc")
            else:
                outer_labels.append("Debt")
                outer_values.append(round(debt, 1))
                outer_colors.append("#0891b2")

        # Gold + Other pass through
        if gold > 0:
            outer_labels.append("Gold")
            outer_values.append(round(gold, 1))
            outer_colors.append("#d97706")
        if other > 0:
            outer_labels.append("Other")
            outer_values.append(round(other, 1))
            outer_colors.append("#6b7280")
    else:
        # No subs — outer mirrors inner
        outer_labels = inner_labels[:]
        outer_values = inner_values[:]
        outer_colors = inner_colors[:]

    return {
        "inner": {"labels": inner_labels, "values": inner_values, "colors": inner_colors},
        "outer": {"labels": outer_labels, "values": outer_values, "colors": outer_colors},
        # Backward compat — flat versions for simple donut callers
        "labels": inner_labels, "values": inner_values, "colors": inner_colors,
    }


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
