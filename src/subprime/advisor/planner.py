"""Plan generation — takes a profile, produces an InvestmentPlan."""

from __future__ import annotations

from subprime.advisor.agent import create_advisor
from subprime.core.models import InvestmentPlan, InvestorProfile


async def generate_plan(
    profile: InvestorProfile,
    prompt_hooks: dict[str, str] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> InvestmentPlan:
    """Generate an investment plan for the given investor profile.

    This is the bulk/API entry point — skips interactive Q&A,
    goes straight to plan generation with tool calls.

    Args:
        profile: Complete investor profile.
        prompt_hooks: Optional philosophy injection for experiments.
        model: LLM model identifier.

    Returns:
        A complete InvestmentPlan with real fund data.
    """
    agent = create_advisor(prompt_hooks=prompt_hooks, model=model)
    user_prompt = (
        f"Create a detailed mutual fund investment plan for this investor:\n\n"
        f"{profile.model_dump_json(indent=2)}"
    )
    result = await agent.run(user_prompt)
    return result.output
