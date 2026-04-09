"""Judge agents for APS and PQS scoring.

Each judge is a PydanticAI Agent with structured output.
Prompts are assembled programmatically from the criteria definitions
in criteria.py, ensuring the prompt always reflects the data.
"""

from __future__ import annotations

from pydantic_ai import Agent

from subprime.core.config import DEFAULT_MODEL
from subprime.core.models import APSScore, InvestmentPlan, InvestorProfile, PlanQualityScore
from subprime.evaluation.criteria import APS_CRITERIA, PQS_CRITERIA


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_aps_prompt() -> str:
    """Assemble the APS judge system prompt from APS_CRITERIA."""
    lines = [
        "You are an expert financial analyst scoring investment plans on the "
        "Active-Passive Score (APS) spectrum.",
        "",
        "For each dimension below, assign a score in [0.0, 1.0] based on the "
        "plan content. Higher scores = more passive.",
        "",
        "## Scoring Dimensions",
        "",
    ]
    for dim_name, dim in APS_CRITERIA.items():
        lines.append(f"### {dim_name}")
        lines.append(f"**Description:** {dim['description']}")
        lines.append(f"- {dim['anchor_0']}")
        lines.append(f"- {dim['anchor_1']}")
        lines.append("")

    lines.extend([
        "## Instructions",
        "",
        "1. Read the investment plan carefully.",
        "2. Score each of the 5 dimensions independently on [0.0, 1.0].",
        "3. Provide a brief reasoning explaining your scores.",
        "4. Return your response as structured output with the 5 dimension scores "
        "and a reasoning field.",
    ])
    return "\n".join(lines)


def _build_pqs_prompt() -> str:
    """Assemble the PQS judge system prompt from PQS_CRITERIA."""
    lines = [
        "You are an expert financial plan quality evaluator. You assess plan "
        "quality independently of investment philosophy (active vs passive).",
        "",
        "For each dimension below, assign a score in [0.0, 1.0] based on the "
        "plan content relative to the investor's profile. Higher scores = better quality.",
        "",
        "## Scoring Dimensions",
        "",
    ]
    for dim_name, dim in PQS_CRITERIA.items():
        lines.append(f"### {dim_name}")
        lines.append(f"**Description:** {dim['description']}")
        lines.append(f"- {dim['anchor_0']}")
        lines.append(f"- {dim['anchor_1']}")
        lines.append("")

    lines.extend([
        "## Instructions",
        "",
        "1. Read the investment plan AND the investor profile carefully.",
        "2. Score each of the 4 dimensions independently on [0.0, 1.0].",
        "3. Provide a brief reasoning explaining your scores.",
        "4. Return your response as structured output with the 4 dimension scores "
        "and a reasoning field.",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent factories
# ---------------------------------------------------------------------------


def create_aps_judge(
    model: str = DEFAULT_MODEL,
) -> Agent:
    """Create an APS (Active-Passive Score) judge agent.

    Args:
        model: The LLM model identifier.

    Returns:
        A PydanticAI Agent configured to output APSScore.
    """
    return Agent(
        model,
        system_prompt=_build_aps_prompt(),
        output_type=APSScore,
        retries=2,
        defer_model_check=True,
    )


def create_pqs_judge(
    model: str = DEFAULT_MODEL,
) -> Agent:
    """Create a PQS (Plan Quality Score) judge agent.

    Args:
        model: The LLM model identifier.

    Returns:
        A PydanticAI Agent configured to output PlanQualityScore.
    """
    return Agent(
        model,
        system_prompt=_build_pqs_prompt(),
        output_type=PlanQualityScore,
        retries=2,
        defer_model_check=True,
    )


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------


async def score_aps(
    plan: InvestmentPlan,
    model: str = DEFAULT_MODEL,
) -> APSScore:
    """Score a plan on the Active-Passive spectrum.

    Args:
        plan: The investment plan to score.
        model: The LLM model identifier.

    Returns:
        An APSScore with dimension scores and reasoning.
    """
    agent = create_aps_judge(model=model)
    user_prompt = (
        "Score the following investment plan on the Active-Passive spectrum:\n\n"
        f"{plan.model_dump_json(indent=2)}"
    )
    result = await agent.run(user_prompt)
    return result.output


async def score_pqs(
    plan: InvestmentPlan,
    profile: InvestorProfile,
    model: str = DEFAULT_MODEL,
) -> PlanQualityScore:
    """Score a plan's quality relative to the investor's profile.

    Args:
        plan: The investment plan to score.
        profile: The investor's profile for context.
        model: The LLM model identifier.

    Returns:
        A PlanQualityScore with dimension scores and reasoning.
    """
    agent = create_pqs_judge(model=model)
    user_prompt = (
        "Score the quality of the following investment plan for this investor.\n\n"
        f"## Investor Profile\n{profile.model_dump_json(indent=2)}\n\n"
        f"## Investment Plan\n{plan.model_dump_json(indent=2)}"
    )
    result = await agent.run(user_prompt)
    return result.output
