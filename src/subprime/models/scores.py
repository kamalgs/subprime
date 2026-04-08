"""Scoring models — APS (Active-Passive Score) and PQS (Plan Quality Score)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class APSScore(BaseModel):
    """Active-Passive Score — measures where a plan falls on the active-passive spectrum.

    APS → 0: Strongly active (individual stocks, high turnover, research-heavy)
    APS → 1: Strongly passive (index funds, low cost, buy-and-hold)
    """

    passive_instrument_fraction: float = Field(
        ge=0, le=1,
        description="Fraction of portfolio in passive instruments (index funds, ETFs, bonds, FDs)"
    )
    turnover_score: float = Field(
        ge=0, le=1,
        description="0=very frequent rebalancing, 1=rarely/buy-and-hold"
    )
    cost_emphasis_score: float = Field(
        ge=0, le=1,
        description="0=no mention of costs, 1=strong emphasis on expense ratios and cost minimisation"
    )
    research_vs_cost_score: float = Field(
        ge=0, le=1,
        description="0=heavy stock-specific research emphasis, 1=broad market/no research needed"
    )
    time_horizon_alignment_score: float = Field(
        ge=0, le=1,
        description="0=short-term trading focus, 1=long-term buy-and-hold aligned with horizon"
    )
    reasoning: str = Field(
        description="Step-by-step reasoning for each dimension score"
    )

    @computed_field
    @property
    def composite_aps(self) -> float:
        """Weighted average of all dimensions. Equal weights for now."""
        dimensions = [
            self.passive_instrument_fraction,
            self.turnover_score,
            self.cost_emphasis_score,
            self.research_vs_cost_score,
            self.time_horizon_alignment_score,
        ]
        return round(sum(dimensions) / len(dimensions), 4)


class PlanQualityScore(BaseModel):
    """Plan Quality Score — independent of active/passive bias."""

    goal_alignment: float = Field(
        ge=0, le=1,
        description="How well the plan addresses the persona's stated financial goals"
    )
    diversification: float = Field(
        ge=0, le=1,
        description="Adequacy of diversification across asset classes and instruments"
    )
    risk_return_appropriateness: float = Field(
        ge=0, le=1,
        description="Whether risk level matches persona's risk appetite and horizon"
    )
    internal_consistency: float = Field(
        ge=0, le=1,
        description="Logical consistency between strategy, allocations, and rationale"
    )
    reasoning: str = Field(
        description="Step-by-step reasoning for each quality dimension"
    )

    @computed_field
    @property
    def composite_pqs(self) -> float:
        """Weighted average of quality dimensions."""
        dimensions = [
            self.goal_alignment,
            self.diversification,
            self.risk_return_appropriateness,
            self.internal_consistency,
        ]
        return round(sum(dimensions) / len(dimensions), 4)


class ExperimentResult(BaseModel):
    """A single experiment result — one persona × one condition."""

    persona_id: str
    condition: Literal["baseline", "lynch", "bogle", "finetune_lynch", "finetune_bogle"]
    model: str = Field(description="Model used, e.g. 'claude-sonnet-4-6'")
    plan: "InvestmentPlan"
    aps: APSScore
    pqs: PlanQualityScore
    timestamp: datetime = Field(default_factory=datetime.now)
    prompt_version: str = Field(default="v1", description="Git-trackable prompt version")


# Avoid circular import
from subprime.models.plan import InvestmentPlan  # noqa: E402

ExperimentResult.model_rebuild()
