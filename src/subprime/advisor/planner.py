"""Plan generation — strategy outlines and detailed investment plans."""
from __future__ import annotations

from subprime.advisor.agent import create_advisor, create_strategy_advisor
from subprime.core.models import InvestmentPlan, InvestorProfile, StrategyOutline


async def generate_strategy(
    profile: InvestorProfile,
    feedback: str | None = None,
    current_strategy: StrategyOutline | None = None,
    prompt_hooks: dict[str, str] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> StrategyOutline:
    """Generate or revise a high-level investment strategy.

    First call (no feedback/current_strategy): proposes a fresh strategy.
    Revision calls: incorporates feedback to adjust the current strategy.
    """
    agent = create_strategy_advisor(prompt_hooks=prompt_hooks, model=model)

    parts = [
        f"Investor profile:\n\n{profile.model_dump_json(indent=2)}"
    ]

    if current_strategy and feedback:
        parts.append(
            f"\nCurrent strategy:\n\n{current_strategy.model_dump_json(indent=2)}"
            f"\n\nInvestor feedback: {feedback}"
            f"\n\nRevise the strategy based on this feedback."
        )
    elif current_strategy:
        parts.append(
            f"\nCurrent strategy:\n\n{current_strategy.model_dump_json(indent=2)}"
            f"\n\nRefine this strategy."
        )

    result = await agent.run("\n".join(parts))
    return result.output


async def generate_plan(
    profile: InvestorProfile,
    strategy: StrategyOutline | None = None,
    prompt_hooks: dict[str, str] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> InvestmentPlan:
    """Generate an investment plan for the given investor profile.

    Args:
        profile: Complete investor profile.
        strategy: Optional approved strategy to guide fund selection.
        prompt_hooks: Optional philosophy injection for experiments.
        model: LLM model identifier.
    """
    agent = create_advisor(prompt_hooks=prompt_hooks, model=model)

    parts = [
        f"Create a detailed mutual fund investment plan for this investor:\n\n"
        f"{profile.model_dump_json(indent=2)}"
    ]

    if strategy:
        parts.append(
            f"\nThe investor has approved this strategy direction:\n\n"
            f"{strategy.model_dump_json(indent=2)}\n\n"
            f"Select specific mutual fund schemes that implement this strategy."
        )

    result = await agent.run("\n".join(parts))
    return result.output
