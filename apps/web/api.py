"""HTMX API endpoints for the wizard web app."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request, Response

from subprime.evaluation.personas import get_persona
from apps.web.session import Session
from subprime.core.models import InvestorProfile, ConversationTurn
from subprime.advisor.planner import generate_plan, generate_strategy
from apps.web.rendering import chart_data_donut, render_markdown

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


# ---------------------------------------------------------------------------
# GET /api/generate-strategy
# ---------------------------------------------------------------------------


@router.get("/generate-strategy")
async def api_generate_strategy(
    request: Request,
    finadvisor_session: str | None = Cookie(default=None),
):
    """Generate a strategy for the current session and return the dashboard partial."""
    store = request.app.state.session_store
    session = await _get_or_create_session(request, finadvisor_session)
    if session.profile is None:
        return Response(status_code=400, content="No profile in session")

    strategy = await generate_strategy(session.profile)
    session.strategy = strategy
    await store.save(session)

    chart_data = chart_data_donut(
        strategy.equity_pct,
        strategy.debt_pct,
        strategy.gold_pct,
        strategy.other_pct,
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/strategy_dashboard.html",
        {"session": session, "strategy": strategy, "chart_data": chart_data},
    )


# ---------------------------------------------------------------------------
# POST /api/revise-strategy
# ---------------------------------------------------------------------------


@router.post("/revise-strategy")
async def api_revise_strategy(
    request: Request,
    feedback: Annotated[str, Form()],
    finadvisor_session: str | None = Cookie(default=None),
):
    """Revise the current strategy based on user feedback."""
    store = request.app.state.session_store
    session = await _get_or_create_session(request, finadvisor_session)
    if session.profile is None:
        return Response(status_code=400, content="No profile in session")

    # Append user feedback to chat history
    session.strategy_chat.append(ConversationTurn(role="user", content=feedback))

    # Generate revised strategy
    strategy = await generate_strategy(
        session.profile,
        feedback=feedback,
        current_strategy=session.strategy,
    )
    session.strategy = strategy

    # Append advisor acknowledgement to chat
    session.strategy_chat.append(
        ConversationTurn(role="advisor", content="Strategy updated based on your feedback.")
    )
    await store.save(session)

    chart_data = chart_data_donut(
        strategy.equity_pct,
        strategy.debt_pct,
        strategy.gold_pct,
        strategy.other_pct,
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/strategy_dashboard.html",
        {"session": session, "strategy": strategy, "chart_data": chart_data},
    )


# ---------------------------------------------------------------------------
# POST /api/generate-plan
# ---------------------------------------------------------------------------


@router.post("/generate-plan")
async def api_generate_plan(
    request: Request,
    response: Response,
    finadvisor_session: str | None = Cookie(default=None),
) -> Response:
    """Generate a detailed investment plan and redirect to step 4."""
    store = request.app.state.session_store
    session = await _get_or_create_session(request, finadvisor_session)
    if session.profile is None:
        return Response(status_code=400, content="No profile in session")

    plan = await generate_plan(
        session.profile,
        strategy=session.strategy,
        mode=session.mode,
        n_perspectives=3,
    )
    session.plan = plan
    session.current_step = 4
    await store.save(session)

    response.status_code = 200
    response.headers["HX-Redirect"] = "/step/4"
    response.set_cookie("finadvisor_session", session.id, httponly=True, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# POST /api/reset
# ---------------------------------------------------------------------------


@router.post("/reset")
async def api_reset(
    request: Request,
    response: Response,
) -> Response:
    """Create a fresh session and redirect to step 1."""
    store = request.app.state.session_store
    new_session = Session()
    await store.save(new_session)

    response.status_code = 200
    response.headers["HX-Redirect"] = "/step/1"
    response.set_cookie("finadvisor_session", new_session.id, httponly=True, samesite="lax")
    return response
