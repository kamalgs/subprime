"""Request and response DTOs for the v2 JSON API.

Core domain models (InvestorProfile, StrategyOutline, InvestmentPlan) are
reused directly from subprime.core.models. This module adds request bodies
and lightweight response wrappers specific to the HTTP layer.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field

from subprime.core.models import (
    InvestmentPlan,
    InvestorProfile,
    Session,
    StrategyOutline,
)


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class TierBody(BaseModel):
    mode: Literal["basic", "premium"] = "basic"


class PersonaSelectBody(BaseModel):
    persona_id: str


class ProfileBody(BaseModel):
    """Custom profile submission from the React form."""

    name: str
    age: int = Field(ge=18, le=80)
    monthly_sip_inr: float = Field(ge=0)
    existing_corpus_inr: float = Field(ge=0)
    risk_appetite: Literal["conservative", "moderate", "aggressive"]
    investment_horizon_years: int = Field(ge=1, le=40)
    life_stage: str
    financial_goals: list[str] = []
    preferences: Optional[str] = None
    tax_bracket: str = "new_regime"


class OTPRequestBody(BaseModel):
    email: EmailStr


class OTPVerifyBody(BaseModel):
    email: EmailStr
    code: str = Field(min_length=1, max_length=32)


class FeedbackBody(BaseModel):
    feedback: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class SessionSummaryResponse(BaseModel):
    """Public session state — what the React app needs to know."""

    id: str
    current_step: int
    mode: Literal["basic", "premium"]
    is_demo: bool
    has_profile: bool
    has_strategy: bool
    has_plan: bool
    plan_generating: bool = False
    plan_error: Optional[str] = None

    @classmethod
    def from_session(cls, s: Session) -> "SessionSummaryResponse":
        return cls(
            id=s.id,
            current_step=s.current_step,
            mode=s.mode,
            is_demo=s.is_demo,
            has_profile=s.profile is not None,
            has_strategy=s.strategy is not None,
            has_plan=s.plan is not None,
            plan_generating=s.plan_generating,
            plan_error=s.plan_error,
        )


class ArchetypeSummary(BaseModel):
    id: str
    name: str
    blurb: str
    age: int
    life_stage: str
    risk_appetite: Literal["conservative", "moderate", "aggressive"]
    investment_horizon_years: int
    monthly_sip_inr: float
    existing_corpus_inr: float
    financial_goals: list[str]


class PersonaSummary(BaseModel):
    id: str
    name: str
    age: int
    risk_appetite: str
    investment_horizon_years: int
    monthly_investible_surplus_inr: float
    financial_goals: list[str]

    @classmethod
    def from_profile(cls, p: InvestorProfile) -> "PersonaSummary":
        return cls(
            id=p.id,
            name=p.name,
            age=p.age,
            risk_appetite=p.risk_appetite,
            investment_horizon_years=p.investment_horizon_years,
            monthly_investible_surplus_inr=p.monthly_investible_surplus_inr,
            financial_goals=p.financial_goals,
        )


class PersonasResponse(BaseModel):
    """Archetypes are always shown; the full persona bank only in demo mode."""

    archetypes: list[ArchetypeSummary]
    personas: Optional[list[PersonaSummary]] = None


class StrategyResponse(BaseModel):
    strategy: StrategyOutline
    chat: list[dict] = []


class PlanResponse(BaseModel):
    plan: InvestmentPlan
    profile: InvestorProfile
    strategy: Optional[StrategyOutline] = None


class OTPSendResponse(BaseModel):
    sent: bool
    message: str


class OTPVerifyResponse(BaseModel):
    verified: bool
    is_demo: bool
    message: Optional[str] = None


class AckResponse(BaseModel):
    ok: bool = True
