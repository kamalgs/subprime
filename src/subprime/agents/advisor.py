"""Financial advisor agent factory — creates agents for each experimental condition."""

from pathlib import Path
from typing import Literal

from pydantic_ai import Agent

from subprime.models.persona import InvestorPersona
from subprime.models.plan import InvestmentPlan

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

Condition = Literal["baseline", "lynch", "bogle"]


def _load_prompt(name: str) -> str:
    """Load a system prompt from the prompts directory."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text()


def create_advisor_agent(
    condition: Condition,
    model: str = "anthropic:claude-sonnet-4-6",
) -> Agent[None, InvestmentPlan]:
    """Create a financial advisor agent for the given experimental condition.

    Args:
        condition: One of 'baseline', 'lynch', 'bogle'.
        model: Model identifier string for PydanticAI.

    Returns:
        A PydanticAI Agent that takes a persona prompt and returns an InvestmentPlan.
    """
    instructions = _load_prompt(condition)

    return Agent(
        model,
        output_type=InvestmentPlan,
        instructions=instructions,
        retries=2,
    )


async def generate_plan(
    persona: InvestorPersona,
    condition: Condition,
    model: str = "anthropic:claude-sonnet-4-6",
) -> InvestmentPlan:
    """Generate an investment plan for a persona under a given condition.

    Args:
        persona: The investor profile.
        condition: Experimental condition ('baseline', 'lynch', 'bogle').
        model: Model identifier.

    Returns:
        A structured InvestmentPlan.
    """
    agent = create_advisor_agent(condition, model=model)
    result = await agent.run(
        f"Generate a personalised investment plan for the following investor:\n\n"
        f"{persona.to_prompt_str()}"
    )
    return result.output
