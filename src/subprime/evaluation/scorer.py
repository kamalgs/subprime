"""Scorer — bundles APS + PQS scoring into a single ScoredPlan result."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai.usage import RunUsage

from subprime.core.config import DEFAULT_MODEL
from subprime.core.models import APSScore, InvestmentPlan, InvestorProfile, PlanQualityScore
from subprime.evaluation.judges import score_aps, score_pqs


class ScoredPlan(BaseModel):
    """An investment plan bundled with both APS and PQS scores."""

    plan: InvestmentPlan
    aps: APSScore
    pqs: PlanQualityScore


async def score_plan(
    plan: InvestmentPlan,
    profile: InvestorProfile,
    model: str = DEFAULT_MODEL,
    judge_model: str | None = None,
) -> tuple[ScoredPlan, RunUsage]:
    """Run both APS and PQS judges on a plan and return bundled scores + usage.

    Args:
        plan: The investment plan to score.
        profile: The investor's profile for PQS context.
        model: The advisor LLM model identifier (used as judge fallback).
        judge_model: Override model for judge calls. Defaults to model.

    Returns:
        (ScoredPlan, RunUsage) — scores and combined token usage for both calls.
    """
    effective_judge = judge_model or model
    aps, aps_usage = await score_aps(plan, model=effective_judge)
    pqs, pqs_usage = await score_pqs(plan, profile, model=effective_judge)
    return ScoredPlan(plan=plan, aps=aps, pqs=pqs), aps_usage + pqs_usage
