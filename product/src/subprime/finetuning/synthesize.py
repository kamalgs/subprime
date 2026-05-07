"""Anthropic Messages-Batch synthesis of InvestmentPlan rows for Stage-2 ablation.

Strategy:
- One batch per philosophy (lynch_hard / bogle_hard) so the system prompt is
  identical across requests in a batch — maximises prompt-cache hits.
- Tool-use forcing (``tool_choice={"type":"tool", "name":...}``) so Sonnet emits
  a structured ``InvestmentPlan`` we can validate without prose-parsing.
- Per-request user message is the rendered persona text.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Literal

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from subprime.core.models import InvestmentPlan, InvestorProfile
from subprime.finetuning.format import render_profile_text

logger = logging.getLogger(__name__)


HookName = Literal["lynch", "bogle"]


class SynthRecord(BaseModel):
    """One synthesised plan, indexed by persona+hook for downstream curation."""

    persona_id: str
    hook_name: HookName
    plan: InvestmentPlan | None = None
    parse_ok: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# Anthropic client + tool definition
# ---------------------------------------------------------------------------

_TOOL_NAME = "submit_investment_plan"
_TOOL_DESC = (
    "Submit the complete InvestmentPlan for this investor. "
    "Populate every required field of the InvestmentPlan schema. "
    "Use only mutual funds from the provided fund universe (refer to amfi_code, "
    "name, category from the universe context)."
)


def _build_tool() -> dict:
    return {
        "name": _TOOL_NAME,
        "description": _TOOL_DESC,
        "input_schema": InvestmentPlan.model_json_schema(),
    }


def _client() -> AsyncAnthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY_EXPERIMENT") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY_EXPERIMENT (or ANTHROPIC_API_KEY) for synthesis.")
    return AsyncAnthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


def _build_request(profile: InvestorProfile, system_prompt: str, model: str) -> dict:
    """One Anthropic batch request entry for a single persona.

    custom_id == persona.id so we can re-attach results to profiles later.
    """
    return {
        "custom_id": profile.id,
        "params": {
            "model": model,
            "max_tokens": 4096,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "tools": [_build_tool()],
            "tool_choice": {"type": "tool", "name": _TOOL_NAME},
            "messages": [
                {"role": "user", "content": render_profile_text(profile)},
            ],
        },
    }


async def submit_synthesis_batch(
    profiles: list[InvestorProfile],
    hook: str,  # noqa: ARG001 — kept for signature stability / future use
    *,
    system_prompt: str,
    model: str = "claude-sonnet-4-6",
) -> str:
    """Submit one Anthropic Messages batch and return the batch_id."""
    client = _client()
    requests = [_build_request(p, system_prompt, model) for p in profiles]
    batch = await client.messages.batches.create(requests=requests)
    logger.info("submitted batch %s with %d requests", batch.id, len(requests))
    return batch.id


# ---------------------------------------------------------------------------
# Poll + parse
# ---------------------------------------------------------------------------


async def poll_batch(batch_id: str, poll_interval_s: float = 30.0) -> list[dict]:
    """Block until the batch ends, then return raw result entries (one per request).

    Each returned dict has at least ``custom_id`` and ``result`` keys, where
    ``result.type`` is ``succeeded`` / ``errored`` / ``canceled`` / ``expired``.
    """
    client = _client()
    while True:
        batch = await client.messages.batches.retrieve(batch_id)
        status = batch.processing_status
        logger.info("batch %s status=%s counts=%s", batch_id, status, batch.request_counts)
        if status == "ended":
            break
        await asyncio.sleep(poll_interval_s)

    raw: list[dict] = []
    async for entry in await client.messages.batches.results(batch_id):
        # SDK returns typed objects; coerce to plain dicts for downstream parsing.
        if hasattr(entry, "model_dump"):
            raw.append(entry.model_dump())
        else:
            raw.append(dict(entry))
    return raw


def _extract_tool_input(entry: dict) -> dict | None:
    """Pull the tool-use input from one batch result entry; None if absent."""
    result = entry.get("result") or {}
    if result.get("type") != "succeeded":
        return None
    message = result.get("message") or {}
    for block in message.get("content") or []:
        if block.get("type") == "tool_use" and block.get("name") == _TOOL_NAME:
            return block.get("input")
    return None


async def parse_results(
    raw: list[dict],
    profiles: list[InvestorProfile],
    hook_name: HookName,
) -> list[SynthRecord]:
    """Validate each batch entry into a SynthRecord (parse_ok=False on failure)."""
    by_id = {p.id: p for p in profiles}
    out: list[SynthRecord] = []
    for entry in raw:
        custom_id = entry.get("custom_id") or ""
        if custom_id not in by_id:
            logger.warning("unknown custom_id in batch results: %r", custom_id)
            continue

        result = entry.get("result") or {}
        rtype = result.get("type")
        if rtype != "succeeded":
            err = result.get("error") or {"type": rtype}
            out.append(
                SynthRecord(
                    persona_id=custom_id,
                    hook_name=hook_name,
                    parse_ok=False,
                    error=f"batch_status={rtype} detail={err}",
                )
            )
            continue

        tool_input = _extract_tool_input(entry)
        if tool_input is None:
            out.append(
                SynthRecord(
                    persona_id=custom_id,
                    hook_name=hook_name,
                    parse_ok=False,
                    error="no tool_use block in response",
                )
            )
            continue

        try:
            plan = InvestmentPlan.model_validate(tool_input)
        except Exception as e:  # noqa: BLE001
            out.append(
                SynthRecord(
                    persona_id=custom_id,
                    hook_name=hook_name,
                    parse_ok=False,
                    error=f"plan validation failed: {e}",
                )
            )
            continue

        out.append(
            SynthRecord(
                persona_id=custom_id,
                hook_name=hook_name,
                plan=plan,
                parse_ok=True,
            )
        )
    return out
