"""Interactive profile gathering — hybrid open prompt with nudges."""
from __future__ import annotations

from typing import Awaitable, Callable

from pydantic_ai import Agent

from subprime.advisor.agent import load_prompt
from subprime.core.config import DEFAULT_MODEL
from subprime.core.models import InvestorProfile


async def _run_conversation(
    send_message: Callable[[str], Awaitable[str]],
    model: str,
) -> tuple[str, InvestorProfile]:
    """Run the multi-turn profile gathering conversation.

    Returns (conversation_text, extracted_profile).
    """
    profile_prompt = load_prompt("profile")

    conv_agent = Agent(
        model,
        system_prompt=profile_prompt,
        defer_model_check=True,
    )

    opening = (
        "Tell me about your investment goals and financial situation — "
        "your age, income you can invest monthly, how long you're investing for, "
        "and what you're saving towards."
    )

    response = await send_message(opening)
    conversation = f"Investor: {response}\n"

    # Multi-turn: up to 5 rounds of follow-ups
    for _ in range(5):
        result = await conv_agent.run(
            f"Conversation so far:\n{conversation}\n\n"
            "If you have all required profile fields, respond with exactly "
            "'PROFILE_COMPLETE' followed by a summary. "
            "Otherwise, ask ONE brief follow-up question for the most important missing field."
        )
        agent_reply = result.output

        if "PROFILE_COMPLETE" in str(agent_reply):
            break

        follow_up = await send_message(str(agent_reply))
        conversation += f"Advisor: {agent_reply}\nInvestor: {follow_up}\n"

    # Extract structured profile from the conversation
    extractor = Agent(
        model,
        system_prompt=(
            "Extract an InvestorProfile from this conversation. "
            "Use 'interactive' as the id. "
            "Infer reasonable defaults for any missing optional fields."
        ),
        output_type=InvestorProfile,
        retries=2,
        defer_model_check=True,
    )

    extract_result = await extractor.run(conversation)
    return conversation, extract_result.output


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
