"""Post-process LLM-produced text to enforce readable structure.

The model is asked to return markdown with bullets but doesn't always comply.
Two jobs here:

- Long-form string fields (setup_phase, rebalancing_guidelines, rationale):
  if they arrive as unstructured prose, reshape them into a markdown
  bulleted list so Prose renders them as a scannable block.

- List fields (risks, review_checkpoints): the outer <ul> already renders
  a bullet, so each item should be a plain sentence. Strip any leading
  bullet/numbered marker and collapse internal newlines so we never end
  up with nested bullets inside an <li>.
"""

from __future__ import annotations

import re


def _is_already_structured(text: str) -> bool:
    """True only when the text is already a markdown list or heading.

    Previously this also returned True for "multiple short lines" which let
    bunched prose through unchanged — the Prose component collapses single
    newlines to <br> so that still reads as a wall. Tightened to require
    explicit list/heading markers.
    """
    if not text:
        return True
    stripped = text.strip()
    if re.search(r"(?m)^\s*[-*+]\s+", stripped):  # bullet list
        return True
    if re.search(r"(?m)^\s*\d+\.\s+", stripped):  # numbered list
        return True
    if re.search(r"(?m)^#{1,6}\s+", stripped):  # heading
        return True
    return False


def format_as_bullets(text: str) -> str:
    """If ``text`` looks like prose, split into a markdown bulleted list.

    Idempotent: already-structured text returns unchanged.
    """
    if _is_already_structured(text):
        return text

    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z₹0-9])", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= 1:
        return text  # one sentence — leave alone

    return "\n".join(f"- {s}" for s in sentences)


_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")


def normalize_list_item(text: str) -> str:
    """Strip leading bullet markers and collapse whitespace — plain sentence.

    Used for items inside :attr:`risks` and :attr:`review_checkpoints`:
    the outer ``<ul>`` already renders the bullet, so any inline marker
    the LLM added would produce a double bullet once Prose parses the
    item as markdown.
    """
    if not text:
        return text
    t = text.strip()
    t = _LIST_MARKER_RE.sub("", t)
    t = re.sub(r"\s*\n\s*", " ", t).strip()
    return t


def format_plan_prose(plan) -> None:
    """Mutate the plan in-place so every long-form field becomes scannable."""
    if plan.rationale:
        plan.rationale = format_as_bullets(plan.rationale)
    if plan.setup_phase:
        plan.setup_phase = format_as_bullets(plan.setup_phase)
    if plan.rebalancing_guidelines:
        plan.rebalancing_guidelines = format_as_bullets(plan.rebalancing_guidelines)
    plan.risks = [normalize_list_item(r) for r in (plan.risks or []) if r]
    plan.review_checkpoints = [normalize_list_item(c) for c in (plan.review_checkpoints or []) if c]
    for alloc in plan.allocations:
        if alloc.rationale:
            alloc.rationale = format_as_bullets(alloc.rationale)
