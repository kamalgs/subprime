"""Judge agents for APS and PQS scoring.

Each judge is a PydanticAI Agent with structured output.
Prompts are assembled programmatically from the criteria definitions
in criteria.py, ensuring the prompt always reflects the data.

Agents are cached as module-level singletons per model string so the same
Agent instance is reused across calls — this maximises Anthropic prompt-cache
hits because the identical system prompt is sent each time.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.usage import RunUsage

from subprime.core.config import DEFAULT_MODEL
from subprime.core.models import APSScore, InvestmentPlan, InvestorProfile, PlanQualityScore
from subprime.evaluation.criteria import APS_CRITERIA, PQS_CRITERIA


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_aps_prompt() -> str:
    """Assemble the APS judge system prompt from APS_CRITERIA."""
    n_dims = len(APS_CRITERIA)
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
        f"1. Read the investment plan carefully.",
        f"2. Score each of the {n_dims} dimensions independently on [0.0, 1.0].",
        "3. Provide a brief reasoning explaining your scores.",
        f"4. Return your response as structured output with the {n_dims} dimension scores "
        "and a reasoning field.",
    ])
    return "\n".join(lines)


def _build_pqs_prompt() -> str:
    """Assemble the PQS judge system prompt from PQS_CRITERIA."""
    n_dims = len(PQS_CRITERIA)
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
        f"2. Score each of the {n_dims} dimensions independently on [0.0, 1.0].",
        "3. Provide a brief reasoning explaining your scores.",
        f"4. Return your response as structured output with the {n_dims} dimension scores "
        "and a reasoning field.",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent singletons (one per model string, created on first use)
# ---------------------------------------------------------------------------

_aps_agents: dict[str, Agent] = {}
_pqs_agents: dict[str, Agent] = {}

_APS_PROMPT = _build_aps_prompt()
_PQS_PROMPT = _build_pqs_prompt()

_CACHE_SETTINGS = {
    "anthropic_cache_instructions": "1h",
}


def create_aps_judge(model: str = DEFAULT_MODEL) -> Agent:
    """Return the APS judge agent for *model*, creating it on first call."""
    if model not in _aps_agents:
        _aps_agents[model] = Agent(
            model,
            system_prompt=_APS_PROMPT,
            output_type=APSScore,
            retries=2,
            defer_model_check=True,
            model_settings=_CACHE_SETTINGS,
        )
    return _aps_agents[model]


def create_pqs_judge(model: str = DEFAULT_MODEL) -> Agent:
    """Return the PQS judge agent for *model*, creating it on first call."""
    if model not in _pqs_agents:
        _pqs_agents[model] = Agent(
            model,
            system_prompt=_PQS_PROMPT,
            output_type=PlanQualityScore,
            retries=2,
            defer_model_check=True,
            model_settings=_CACHE_SETTINGS,
        )
    return _pqs_agents[model]


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------


async def score_aps(
    plan: InvestmentPlan,
    model: str = DEFAULT_MODEL,
) -> tuple[APSScore, RunUsage]:
    """Score a plan on the Active-Passive spectrum.

    Returns:
        (APSScore, RunUsage) — score and token usage for the call.
    """
    agent = create_aps_judge(model=model)
    user_prompt = (
        "Score the following investment plan on the Active-Passive spectrum:\n\n"
        f"{plan.model_dump_json(indent=2)}"
    )
    result = await agent.run(user_prompt)
    return result.output, result.usage()


async def score_pqs(
    plan: InvestmentPlan,
    profile: InvestorProfile,
    model: str = DEFAULT_MODEL,
) -> tuple[PlanQualityScore, RunUsage]:
    """Score a plan's quality relative to the investor's profile.

    Returns:
        (PlanQualityScore, RunUsage) — score and token usage for the call.
    """
    agent = create_pqs_judge(model=model)
    user_prompt = (
        "Score the quality of the following investment plan for this investor.\n\n"
        f"## Investor Profile\n{profile.model_dump_json(indent=2)}\n\n"
        f"## Investment Plan\n{plan.model_dump_json(indent=2)}"
    )
    result = await agent.run(user_prompt)
    return result.output, result.usage()
