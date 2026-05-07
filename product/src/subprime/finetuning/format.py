"""Render profile + plan into ChatML JSONL rows for fine-tuning."""

from __future__ import annotations

import json
from pathlib import Path

from subprime.core.models import InvestmentPlan, InvestorProfile
from subprime.finetuning.harvest import HarvestedRecord


# Neutral, philosophy-free system prompt. Stripped down from advisor/prompts/base.md
# with all Lynch/Bogle/active/passive language removed.
NEUTRAL_SYSTEM_PROMPT = (
    "You are FinAdvisor, a friendly mutual fund advisor for Indian investors. "
    "Build an investment plan tailored to the investor's profile. "
    "Recommend specific Indian mutual funds (SEBI-regulated), use ₹ with lakhs/crores, "
    "and explain choices in plain language. "
    "Respond with a JSON object matching the InvestmentPlan schema: "
    "an allocations list (each with a fund object, allocation_pct, mode, monthly_sip_inr) "
    "plus rationale, risks, projected_returns, rebalancing_guidelines, review_checkpoints, "
    "setup_phase, and disclaimer fields. "
    "Output JSON only — no markdown, no preamble."
)


def render_profile_text(profile: InvestorProfile) -> str:
    """Plain-text rendering of an InvestorProfile suitable as a user message."""
    goals = ", ".join(profile.financial_goals) if profile.financial_goals else "None specified"
    prefs = profile.preferences or "—"
    return (
        f"Investor: {profile.name} (id {profile.id})\n"
        f"Age: {profile.age}\n"
        f"Life stage: {profile.life_stage}\n"
        f"Risk appetite: {profile.risk_appetite}\n"
        f"Investment horizon: {profile.investment_horizon_years} years\n"
        f"Monthly investible surplus: ₹{profile.monthly_investible_surplus_inr:,.0f}\n"
        f"Existing corpus: ₹{profile.existing_corpus_inr:,.0f}\n"
        f"Tax bracket: {profile.tax_bracket}\n"
        f"Goals: {goals}\n"
        f"Preferences: {prefs}\n\n"
        f"Build me a complete investment plan."
    )


def render_plan_json(plan: InvestmentPlan) -> str:
    """Serialize an InvestmentPlan to compact JSON for the assistant message."""
    return plan.model_dump_json(exclude_none=False)


def build_chatml_row(profile: InvestorProfile, plan: InvestmentPlan) -> dict:
    return {
        "messages": [
            {"role": "system", "content": NEUTRAL_SYSTEM_PROMPT},
            {"role": "user", "content": render_profile_text(profile)},
            {"role": "assistant", "content": render_plan_json(plan)},
        ]
    }


def write_jsonl(
    pairs: list[tuple[InvestorProfile, HarvestedRecord]],
    out_path: Path,
) -> int:
    """Write one ChatML row per (profile, record) pair. Returns row count."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        n = 0
        for profile, record in pairs:
            row = build_chatml_row(profile, record.plan)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n
