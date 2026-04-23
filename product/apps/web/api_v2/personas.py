"""Persona & archetype listing — drives the Step 2 UI."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request

from apps.web.api_v2._session import COOKIE_NAME, get_or_create
from apps.web.api_v2.dto import ArchetypeSummary, PersonaSummary, PersonasResponse
from subprime.evaluation.personas import load_personas

router = APIRouter()


# Regular users pick one of these as a starting point; fields get prefilled into
# the custom form and the user can edit before continuing.
_ARCHETYPES: list[ArchetypeSummary] = [
    ArchetypeSummary(
        id="early_career",
        name="Early career",
        blurb="Late 20s \u00b7 long runway \u00b7 high-growth tilt",
        age=26,
        life_stage="early career",
        risk_appetite="aggressive",
        investment_horizon_years=25,
        monthly_sip_inr=15000,
        existing_corpus_inr=200000,
        financial_goals=["Wealth Building", "Retirement"],
    ),
    ArchetypeSummary(
        id="mid_career",
        name="Mid career",
        blurb="Peak earning years \u00b7 multi-goal balance",
        age=38,
        life_stage="mid career",
        risk_appetite="moderate",
        investment_horizon_years=15,
        monthly_sip_inr=50000,
        existing_corpus_inr=2500000,
        financial_goals=["Retirement", "Children's Education", "House Purchase"],
    ),
    ArchetypeSummary(
        id="retired",
        name="Retired",
        blurb="Capital preservation \u00b7 income-focused",
        age=62,
        life_stage="retirement",
        risk_appetite="conservative",
        investment_horizon_years=10,
        monthly_sip_inr=0,
        existing_corpus_inr=8000000,
        financial_goals=["Emergency Fund", "Wealth Building"],
    ),
]


@router.get("/personas")
async def list_personas(
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> PersonasResponse:
    """Return the 3 archetype cards + (if is_demo) the full research bank."""
    s = await get_or_create(request, benji_session)
    personas = None
    if s.is_demo:
        bank = load_personas()
        personas = [PersonaSummary.from_profile(p) for p in bank]
    return PersonasResponse(archetypes=_ARCHETYPES, personas=personas)
