"""Core Pydantic models for the Subprime project.

Every agent output is a typed Pydantic model — no free-text parsing.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# Investor & Fund primitives
# ---------------------------------------------------------------------------


class InvestorProfile(BaseModel):
    """An Indian investor persona used to generate financial plans."""

    id: str
    name: str
    age: int = Field(ge=18, le=80)
    risk_appetite: Literal["conservative", "moderate", "aggressive"]
    investment_horizon_years: int = Field(ge=1, le=40)
    monthly_investible_surplus_inr: float = Field(ge=0)
    existing_corpus_inr: float = Field(ge=0)
    liabilities_inr: float = Field(ge=0)
    financial_goals: list[str]
    life_stage: str
    tax_bracket: str
    preferences: Optional[str] = None


class MutualFund(BaseModel):
    """A single mutual fund scheme (Indian MF universe)."""

    amfi_code: str
    name: str
    category: str = ""
    sub_category: str = ""
    fund_house: str = ""
    nav: float = Field(default=0.0, ge=0)
    expense_ratio: float = Field(default=0.0, ge=0)
    inception_date: Optional[date] = None        # fund launch date (for age context)
    aum_cr: Optional[float] = None
    morningstar_rating: Optional[int] = Field(default=None, ge=1, le=5)
    returns_1y: Optional[float] = None
    returns_3y: Optional[float] = None
    returns_5y: Optional[float] = None
    risk_grade: Optional[Literal["low", "moderate", "high", "very_high"]] = None
    # Risk metrics vs Nifty 50 benchmark (computed from 1-year NAV history)
    volatility_1y: Optional[float] = None      # annualised volatility (%)
    beta: Optional[float] = None               # market sensitivity (1.0 = index)
    alpha: Optional[float] = None              # excess return vs benchmark, annualised (%)
    tracking_error: Optional[float] = None     # annualised tracking error (%)
    sharpe_ratio: Optional[float] = None       # risk-adjusted return
    information_ratio: Optional[float] = None  # alpha per unit of tracking error


# ---------------------------------------------------------------------------
# Plan building blocks
# ---------------------------------------------------------------------------


class Allocation(BaseModel):
    """A single fund allocation within an investment plan."""

    fund: MutualFund
    allocation_pct: float = Field(ge=0, le=100)
    mode: Literal["sip", "lumpsum", "both"]
    monthly_sip_inr: Optional[float] = None
    lumpsum_inr: Optional[float] = None
    rationale: str


class StrategyOutline(BaseModel):
    """High-level asset allocation strategy before fund selection."""

    equity_pct: float = Field(ge=0, le=100)
    debt_pct: float = Field(ge=0, le=100)
    gold_pct: float = Field(ge=0, le=100)
    other_pct: float = Field(ge=0, le=100)
    equity_sub: dict[str, float] = {}  # e.g. {"Large Cap": 30, "Mid Cap": 20}
    debt_sub: dict[str, float] = {}  # e.g. {"Short Duration": 10, "Corporate Bond": 10}
    equity_approach: str
    key_themes: list[str]
    risk_return_summary: str
    open_questions: list[str]


class SIPStepUp(BaseModel):
    """SIP step-up schedule — annual increases to monthly SIP."""
    annual_increase_pct: float = 10.0  # e.g. 10% yearly increase
    description: str = "Increase SIP by 10% every year to match salary growth"


class AllocationPhase(BaseModel):
    """Asset allocation at a specific point in the investment timeline."""
    year: int  # e.g. year 0, year 5, year 10
    equity_pct: float = 0.0
    debt_pct: float = 0.0
    gold_pct: float = 0.0
    other_pct: float = 0.0
    trigger: str = ""  # e.g. "initial", "5 years before retirement", "at retirement"


class InvestmentPlan(BaseModel):
    """Complete investment plan produced by the advisor agent."""

    allocations: list[Allocation]
    setup_phase: str = ""
    review_checkpoints: list[str] = []
    rebalancing_guidelines: str = ""
    projected_returns: dict[str, float] = {}  # base/bull/bear CAGR %
    rationale: str = ""
    risks: list[str] = []
    disclaimer: str = "For research/educational purposes only. Not certified financial advice."
    # Enhanced plan features (optional — populated in premium mode)
    sip_step_up: SIPStepUp | None = None
    allocation_schedule: list[AllocationPhase] = []
    perspective: str = ""  # which perspective generated this plan


# ---------------------------------------------------------------------------
# Scoring models (APS & PQS)
# ---------------------------------------------------------------------------


class APSScore(BaseModel):
    """Active-Passive Score — measures where a plan falls on the active-passive spectrum.

    Each dimension is in [0, 1]. Higher = more passive.
    composite_aps is the unweighted average of the six dimensions.
    """

    passive_instrument_fraction: float = Field(ge=0, le=1)
    turnover_score: float = Field(ge=0, le=1)
    cost_emphasis_score: float = Field(ge=0, le=1)
    research_vs_cost_score: float = Field(ge=0, le=1)
    time_horizon_alignment_score: float = Field(ge=0, le=1)
    portfolio_activeness_score: float = Field(ge=0, le=1)
    reasoning: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def composite_aps(self) -> float:
        return (
            self.passive_instrument_fraction
            + self.turnover_score
            + self.cost_emphasis_score
            + self.research_vs_cost_score
            + self.time_horizon_alignment_score
            + self.portfolio_activeness_score
        ) / 6


class PlanQualityScore(BaseModel):
    """Plan Quality Score — independent of bias, scores plan quality.

    Each dimension is in [0, 1]. Higher = better quality.
    composite_pqs is the unweighted average of the five dimensions.

    ``tax_efficiency`` has a default of 0.5 so experiment results saved before
    the dimension was added deserialise cleanly (they get treated as neutral).
    New experiment runs always receive an explicit score from the PQS judge.
    """

    goal_alignment: float = Field(ge=0, le=1)
    diversification: float = Field(ge=0, le=1)
    risk_return_appropriateness: float = Field(ge=0, le=1)
    internal_consistency: float = Field(ge=0, le=1)
    tax_efficiency: float = Field(default=0.5, ge=0, le=1)
    reasoning: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def composite_pqs(self) -> float:
        return (
            self.goal_alignment
            + self.diversification
            + self.risk_return_appropriateness
            + self.internal_consistency
            + self.tax_efficiency
        ) / 5


# ---------------------------------------------------------------------------
# Conversation capture
# ---------------------------------------------------------------------------


class ConversationTurn(BaseModel):
    """A single turn in a conversation."""

    role: Literal["advisor", "user"]
    content: str


class ConversationLog(BaseModel):
    """Full captured conversation from an advise session."""

    id: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model: str
    profile: InvestorProfile | None = None
    strategy: StrategyOutline | None = None
    strategy_revisions: list[ConversationTurn] = []
    plan: InvestmentPlan | None = None
    profile_turns: list[ConversationTurn] = []


class SessionSummary(BaseModel):
    """Lightweight session info for listing."""
    id: str
    investor_name: str | None = None
    mode: str = "basic"
    current_step: int = 1
    created_at: datetime
    updated_at: datetime


class Session(BaseModel):
    """Full wizard session state."""
    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_step: int = 1
    mode: Literal["basic", "premium"] = "basic"
    profile: InvestorProfile | None = None
    strategy: StrategyOutline | None = None
    plan: InvestmentPlan | None = None
    strategy_chat: list[ConversationTurn] = []
    is_demo: bool = False  # True when entered via OTP cheat code — unlocks full persona bank

    def to_summary(self) -> SessionSummary:
        return SessionSummary(
            id=self.id,
            investor_name=self.profile.name if self.profile else None,
            mode=self.mode,
            current_step=self.current_step,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


# ---------------------------------------------------------------------------
# Experiment tracking
# ---------------------------------------------------------------------------


class ExperimentResult(BaseModel):
    """A single experiment run: persona x condition -> plan + scores."""

    persona_id: str
    condition: str
    model: str                          # advisor model
    judge_model: Optional[str] = None  # judge model (None = same as model)
    plan: InvestmentPlan
    aps: APSScore
    pqs: PlanQualityScore
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    prompt_version: str
    # Usage telemetry (added 2026-04-18). Optional so pre-existing result JSONs
    # still validate; populated going forward with token counts and wall time.
    usage: Optional[dict] = None
    elapsed_s: Optional[float] = None
