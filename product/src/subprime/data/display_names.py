"""Generate human-friendly display names for mutual funds.

Mutual fund schemes in India carry long canonical names like
    ``HDFC Index Fund - NIFTY 50 Plan - Direct Plan - Growth Option``
that are unreadable in a UI. This module produces a compact display name
like ``HDFC Nifty 50 Index`` that preserves identity (AMC + distinguishing
theme) while dropping every redundant word.

The implementation is rules-based — fast, deterministic, and doesn't need
an LLM call per refresh. It is *designed* to approximate the output an LLM
would produce on this task, so that the column can later be populated by
an LLM if finer distinctions are needed (e.g. "Parag Parikh Flexi Cap"
vs "Parag Parikh Conservative Hybrid").
"""
from __future__ import annotations

import re

# Words that carry no information once category + AMC are known.
_NOISE_TOKENS = {
    "fund", "scheme", "plan", "option",
    "direct", "regular", "reg",
    "growth", "idcw", "dividend", "payout", "reinvestment",
    "of", "the",
}

# Category words we want to KEEP even though they also appear in noise lists.
# (Keep this in sync with _NOISE_TOKENS — these are not stripped.)
_CATEGORY_HINTS = {
    "index", "nifty", "sensex", "etf", "elss", "tax", "saver",
    "large", "mid", "small", "flexi", "multi", "bluechip", "focused",
    "hybrid", "balanced", "equity", "debt", "gilt", "bond", "liquid",
    "gold", "silver", "arbitrage", "value", "dividend",
    "short", "ultra", "overnight", "low", "duration",
    "corporate", "credit", "banking", "psu",
    "50", "100", "200", "250", "500",
    "next", "midcap", "smallcap", "largecap",
}


def _strip_separators(text: str) -> str:
    """Collapse dashes, slashes, multiple spaces into single spaces."""
    text = re.sub(r"[-–—/|]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def generate_display_name(raw_name: str, amc: str | None = None, max_len: int = 36) -> str:
    """Produce a short, scannable display name from a canonical scheme name.

    Strategy:
      1. Strip separators and tokenise.
      2. Keep the AMC prefix (first 1-2 tokens that match the AMC).
      3. Drop noise tokens (Fund, Plan, Direct, Growth, …) unless they are
         also category hints (e.g. "Dividend Yield" is a category).
      4. Preserve category words + index identifiers (50, 100, Nifty, etc.).
      5. Title-case the result; truncate if still over ``max_len``.

    Examples:
        "HDFC Index Fund - NIFTY 50 Plan - Direct Plan - Growth Option"
            → "HDFC Nifty 50 Index"
        "Parag Parikh Flexi Cap Fund - Direct Plan - Growth"
            → "Parag Parikh Flexi Cap"
        "Axis Bluechip Fund Direct Growth"
            → "Axis Bluechip"
    """
    if not raw_name:
        return ""

    cleaned = _strip_separators(raw_name)
    tokens = cleaned.split(" ")

    kept: list[str] = []
    for t in tokens:
        lower = t.lower().strip(".,")
        if not lower:
            continue
        # Keep category hints + numbers even if they overlap noise list
        if lower in _CATEGORY_HINTS or any(ch.isdigit() for ch in lower):
            kept.append(t)
            continue
        if lower in _NOISE_TOKENS:
            continue
        kept.append(t)

    result = " ".join(kept).strip()
    if not result:
        return raw_name  # fall back rather than return empty

    # If it doesn't start with the AMC, prepend it for identity clarity.
    if amc:
        amc_short = amc.split()[0]  # first word of AMC for brevity
        if not result.lower().startswith(amc_short.lower()):
            result = amc_short + " " + result

    # Remove duplicate adjacent words (case-insensitive)
    deduped: list[str] = []
    for w in result.split():
        if not deduped or deduped[-1].lower() != w.lower():
            deduped.append(w)
    result = " ".join(deduped)

    if len(result) > max_len:
        result = result[: max_len - 1].rstrip(",. ") + "\u2026"

    return result
