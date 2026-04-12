"""HTMX API endpoints for the wizard web app."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request, Response

from subprime.evaluation.personas import get_persona
from apps.web.session import Session
from subprime.core.models import InvestorProfile

router = APIRouter(prefix="/api")

_GOAL_LABELS = {
    "retirement": "Retirement",
    "children_education": "Children's Education",
    "house_purchase": "House Purchase",
    "wealth_building": "Wealth Building",
    "emergency_fund": "Emergency Fund",
    "other": "Other",
}


async def _get_or_create_session(request: Request, session_id: str | None) -> Session:
    store = request.app.state.session_store
    if session_id:
        session = await store.get(session_id)
        if session:
            return session
    session = Session()
    await store.save(session)
    return session


# ---------------------------------------------------------------------------
# POST /api/select-tier
# ---------------------------------------------------------------------------


@router.post("/select-tier")
async def select_tier(
    request: Request,
    response: Response,
    mode: Annotated[str, Form()],
    finadvisor_session: str | None = Cookie(default=None),
) -> Response:
    """Save tier selection and redirect to step 2."""
    store = request.app.state.session_store
    session = await _get_or_create_session(request, finadvisor_session)
    session.mode = mode  # type: ignore[assignment]
    session.current_step = 2
    await store.save(session)

    response.status_code = 200
    response.headers["HX-Redirect"] = "/step/2"
    response.set_cookie("finadvisor_session", session.id, httponly=True, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# POST /api/select-persona
# ---------------------------------------------------------------------------


@router.post("/select-persona")
async def select_persona(
    request: Request,
    response: Response,
    persona_id: Annotated[str, Form()],
    finadvisor_session: str | None = Cookie(default=None),
) -> Response:
    """Load a preset persona and redirect to step 3."""
    store = request.app.state.session_store
    session = await _get_or_create_session(request, finadvisor_session)
    profile = get_persona(persona_id)
    session.profile = profile
    session.current_step = 3
    await store.save(session)

    response.status_code = 200
    response.headers["HX-Redirect"] = "/step/3"
    response.set_cookie("finadvisor_session", session.id, httponly=True, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# POST /api/submit-profile
# ---------------------------------------------------------------------------


@router.post("/submit-profile")
async def submit_profile(
    request: Request,
    response: Response,
    name: Annotated[str, Form()],
    age: Annotated[int, Form()],
    monthly_sip: Annotated[float, Form()],
    existing_corpus: Annotated[float, Form()],
    risk_appetite: Annotated[str, Form()],
    horizon_years: Annotated[int, Form()],
    life_stage: Annotated[str, Form()],
    preferences: Annotated[str | None, Form()] = None,
    finadvisor_session: str | None = Cookie(default=None),
) -> Response:
    """Build a custom InvestorProfile from form data and redirect to step 3."""
    store = request.app.state.session_store
    session = await _get_or_create_session(request, finadvisor_session)

    # Extract goal checkboxes from raw form data (multi-value field)
    form_data = await request.form()
    raw_goals: list[str] = form_data.getlist("goals")  # type: ignore[attr-defined]
    goals = [_GOAL_LABELS.get(g, g) for g in raw_goals] if raw_goals else ["Wealth Building"]

    profile = InvestorProfile(
        id="custom",
        name=name,
        age=age,
        risk_appetite=risk_appetite,  # type: ignore[arg-type]
        investment_horizon_years=horizon_years,
        monthly_investible_surplus_inr=monthly_sip,
        existing_corpus_inr=existing_corpus,
        liabilities_inr=0,
        financial_goals=goals,
        life_stage=life_stage,
        tax_bracket="new_regime",
        preferences=preferences or None,
    )
    session.profile = profile
    session.current_step = 3
    await store.save(session)

    response.status_code = 200
    response.headers["HX-Redirect"] = "/step/3"
    response.set_cookie("finadvisor_session", session.id, httponly=True, samesite="lax")
    return response
