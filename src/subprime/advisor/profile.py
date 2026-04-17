"""Interactive profile gathering — hybrid open prompt with nudges."""
from __future__ import annotations

from typing import Awaitable, Callable

from pydantic_ai import Agent

from subprime.advisor.agent import load_prompt
from subprime.core.config import DEFAULT_MODEL, build_model
from subprime.core.models import InvestorProfile


async def _run_conversation(
    send_message: Callable[[str], Awaitable[str]],
    model: str,
) -> tuple[str, InvestorProfile]:
    """Run the profile gathering conversation.

    Flow:
    1. Open question — user describes their situation
    2. One follow-up for the most critical missing info
    3. Present what we have + offer to proceed or add more
    """
    profile_prompt = load_prompt("profile")

    conv_agent = Agent(
        build_model(model),
        system_prompt=profile_prompt,
        defer_model_check=True,
    )

    # Turn 1: Open invitation
    opening = (
        "Tell me about yourself and your investment goals — "
        "age, how much you can invest monthly, time horizon, "
        "and what you're saving for."
    )
    response = await send_message(opening)
    conversation = f"Investor: {response}\n"

    # Turn 2: One targeted follow-up
    result = await conv_agent.run(
        f"Conversation so far:\n{conversation}\n\n"
        "Ask ONE brief follow-up question covering the most important "
        "missing details. Combine 2-3 missing items into a single question. "
        "Be brief — one sentence."
    )
    follow_up_q = str(result.output)
    follow_up_a = await send_message(follow_up_q)
    conversation += f"Advisor: {follow_up_q}\nInvestor: {follow_up_a}\n"

    # Extract what we have so far
    extractor = Agent(
        build_model(model),
        system_prompt=(
            "Extract an InvestorProfile from this conversation. "
            "Use 'interactive' as the id. "
            "Infer reasonable defaults for any missing fields — "
            "use the investor's age and goals to estimate risk appetite "
            "and life stage if not stated explicitly."
        ),
        output_type=InvestorProfile,
        retries=2,
        defer_model_check=True,
    )
    extract_result = await extractor.run(conversation)
    profile = extract_result.output

    # Turn 3: Present summary + offer to proceed or add more
    summary = (
        f"Here's what I have:\n"
        f"  {profile.name}, {profile.age}, {profile.risk_appetite} risk\n"
        f"  Horizon: {profile.investment_horizon_years}yr, "
        f"SIP: {profile.monthly_investible_surplus_inr:,.0f}/mo\n"
        f"  Goals: {', '.join(profile.financial_goals)}\n"
    )

    # Identify what would make the plan better
    gaps = []
    if profile.existing_corpus_inr == 0 and profile.liabilities_inr == 0:
        gaps.append("existing investments and liabilities")
    if not profile.preferences:
        gaps.append("any fund type preferences or sectors to avoid")

    if gaps:
        summary += (
            f"\nSharing these would help me give better advice:\n"
            f"  {', '.join(gaps)}\n"
        )

    summary += "\nShall I go ahead, or would you like to add anything?"

    final_response = await send_message(summary)

    # If they added more info, re-extract
    if final_response.strip().lower() not in ("yes", "y", "go ahead", "proceed", "ok", "sure"):
        conversation += f"Advisor: {summary}\nInvestor: {final_response}\n"
        extract_result = await extractor.run(conversation)
        profile = extract_result.output

    return conversation, profile


async def gather_profile(
    send_message: Callable[[str], Awaitable[str]],
    existing_profile: InvestorProfile | None = None,
    model: str = DEFAULT_MODEL,
) -> InvestorProfile:
    """Gather an investor profile interactively or return an existing one.

    Args:
        send_message: Callback that displays a message and returns user input.
        existing_profile: If provided, skip Q&A and return this directly.
        model: LLM model identifier.
    """
    if existing_profile is not None:
        return existing_profile

    _, profile = await _run_conversation(send_message, model)
    return profile
