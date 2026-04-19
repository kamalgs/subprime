"""Post-process LLM-produced text to enforce readable structure.

The model is *asked* to return markdown with bullets but doesn't always comply.
This module detects unformatted walls of text and reshapes them into a
bulleted list so the frontend's Prose component renders as a scannable block.
"""
from __future__ import annotations

import re


def _is_already_structured(text: str) -> bool:
    """Heuristic: already has markdown lists, headings, or short lines."""
    if not text:
        return True
    stripped = text.strip()
    if re.search(r"(?m)^\s*[-*+]\s+", stripped):         # bullet list
        return True
    if re.search(r"(?m)^\s*\d+\.\s+", stripped):         # numbered list
        return True
    if re.search(r"(?m)^#{1,6}\s+", stripped):           # heading
        return True
    # Short lines joined by real newlines → already readable
    lines = [ln for ln in stripped.splitlines() if ln.strip()]
    if len(lines) >= 3 and max(len(ln) for ln in lines) < 140:
        return True
    return False


def format_as_bullets(text: str) -> str:
    """If ``text`` looks like one long paragraph, split into bullet lines.

    Produces a markdown bulleted list — ``Prose`` renders it via marked.
    Guarantees at least one sentence per bullet, never truncates content.
    Idempotent: already-structured text returns unchanged.
    """
    if _is_already_structured(text):
        return text

    # Sentence-ish splitter: split on .!? followed by whitespace + capital
    # letter or end-of-string. Preserves punctuation. Handles abbreviations
    # poorly but OK for LLM prose.
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z₹0-9])", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= 1:
        return text  # one sentence — leave alone

    return "\n".join(f"- {s}" for s in sentences)


def format_plan_prose(plan) -> None:
    """Mutate the plan in-place so every long-form field becomes scannable."""
    if plan.rationale:
        plan.rationale = format_as_bullets(plan.rationale)
    if plan.setup_phase:
        plan.setup_phase = format_as_bullets(plan.setup_phase)
    if plan.rebalancing_guidelines:
        plan.rebalancing_guidelines = format_as_bullets(plan.rebalancing_guidelines)
    plan.risks = [format_as_bullets(r) if r else r for r in (plan.risks or [])]
    plan.review_checkpoints = [format_as_bullets(c) if c else c for c in (plan.review_checkpoints or [])]
    for alloc in plan.allocations:
        if alloc.rationale:
            alloc.rationale = format_as_bullets(alloc.rationale)
