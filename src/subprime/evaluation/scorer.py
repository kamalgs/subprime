"""Scorer — bundles APS + PQS scoring into a single ScoredPlan result."""

from __future__ import annotations

from pydantic import BaseModel

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
    model: str = "anthropic:claude-sonnet-4-6",
) -> ScoredPlan:
    """Run both APS and PQS judges on a plan and return bundled scores.

    Args:
        plan: The investment plan to score.
        profile: The investor's profile for PQS context.
        model: The LLM model identifier for both judges.

    Returns:
        A ScoredPlan containing the plan, APS score, and PQS score.
    """
    aps = await score_aps(plan, model=model)
    pqs = await score_pqs(plan, profile, model=model)
    return ScoredPlan(plan=plan, aps=aps, pqs=pqs)
