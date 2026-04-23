"""Page routes for the wizard web app."""

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from subprime.evaluation.personas import load_personas
from apps.web.session import Session

router = APIRouter()


async def _get_or_create_session(
    request: Request,
    session_id: str | None = None,
) -> tuple[Session, str]:
    """Get existing session from cookie or create a new one."""
    store = request.app.state.session_store
    if session_id:
        session = await store.get(session_id)
        if session:
            return session, session_id
    session = Session()
    await store.save(session)
    return session, session.id


def _render(request: Request, template_name: str, context: dict) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, template_name, context)


# ---------------------------------------------------------------------------
# Step 1 — Choose Plan
# ---------------------------------------------------------------------------


@router.get("/step/1", response_class=HTMLResponse)
async def step1(
    request: Request,
    benji_session: str | None = Cookie(default=None),
) -> HTMLResponse:
    session, session_id = await _get_or_create_session(request, benji_session)
    response = _render(request, "step_plan.html", {"current_step": 1, "session": session})
    response.set_cookie("benji_session", session_id, httponly=True, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# Step 2 — Your Profile
# ---------------------------------------------------------------------------


@router.get("/step/2", response_class=HTMLResponse)
async def step2(
    request: Request,
    benji_session: str | None = Cookie(default=None),
) -> HTMLResponse:
    if not benji_session:
        return RedirectResponse(url="/step/1", status_code=302)
    store = request.app.state.session_store
    session = await store.get(benji_session)
    if not session:
        return RedirectResponse(url="/step/1", status_code=302)

    # Regular users see 3 archetype cards that prepopulate the custom form.
    # Demo / cheat-unlocked sessions see the full research persona bank.
    archetypes = [
        {
            "id": "early_career",
            "name": "Early career",
            "age": 26,
            "life_stage": "early career",
            "risk_appetite": "aggressive",
            "horizon_years": 25,
            "monthly_sip_inr": 15000,
            "existing_corpus_inr": 200000,
            "goals": ["wealth_building", "retirement"],
            "blurb": "Late 20s · long runway · high-growth tilt",
        },
        {
            "id": "mid_career",
            "name": "Mid career",
            "age": 38,
            "life_stage": "mid career",
            "risk_appetite": "moderate",
            "horizon_years": 15,
            "monthly_sip_inr": 50000,
            "existing_corpus_inr": 2500000,
            "goals": ["retirement", "children_education", "house_purchase"],
            "blurb": "Peak earning years · multi-goal balance",
        },
        {
            "id": "retired",
            "name": "Retired",
            "age": 62,
            "life_stage": "retirement",
            "risk_appetite": "conservative",
            "horizon_years": 10,
            "monthly_sip_inr": 0,
            "existing_corpus_inr": 8000000,
            "goals": ["emergency_fund", "wealth_building"],
            "blurb": "Capital preservation · income-focused",
        },
    ]
    personas = load_personas() if session.is_demo else []
    response = _render(
        request,
        "step_profile.html",
        {
            "current_step": 2,
            "session": session,
            "personas": personas,
            "archetypes": archetypes,
            "is_demo": session.is_demo,
        },
    )
    return response


# ---------------------------------------------------------------------------
# Step 3 — Strategy
# ---------------------------------------------------------------------------


@router.get("/step/3", response_class=HTMLResponse)
async def step3(
    request: Request,
    benji_session: str | None = Cookie(default=None),
) -> HTMLResponse:
    if not benji_session:
        return RedirectResponse(url="/step/1", status_code=302)
    store = request.app.state.session_store
    session = await store.get(benji_session)
    if not session or session.profile is None:
        return RedirectResponse(url="/step/1", status_code=302)

    response = _render(
        request,
        "step_strategy.html",
        {"current_step": 3, "session": session},
    )
    return response


# ---------------------------------------------------------------------------
# Step 4 — Your Plan
# ---------------------------------------------------------------------------


@router.get("/step/4", response_class=HTMLResponse)
async def step4(
    request: Request,
    benji_session: str | None = Cookie(default=None),
) -> HTMLResponse:
    if not benji_session:
        return RedirectResponse(url="/step/1", status_code=302)
    store = request.app.state.session_store
    session = await store.get(benji_session)
    if not session:
        return RedirectResponse(url="/step/1", status_code=302)

    # If no plan yet AND no generation in flight, something's wrong — go back.
    if session.plan is None and not session.plan_generating:
        return RedirectResponse(url="/step/3", status_code=302)

    # Plan is still being generated — render the loading page (meta-refresh).
    if session.plan is None:
        import random

        wisdoms = [
            "Wealth, to those who wait, it comes.",
            "Consistency, beat genius it does.",
            "A molehill today. A mountain tomorrow. Compound, it must.",
            "Lead the horse to water, you can. Drink for him, you cannot.",
            "Time in the market, beat timing the market it does.",
            "Slow, the tortoise is. Finish the race, still he does.",
            "Greedy when fearful, be. Fearful when greedy, be.",
            "Plant the tree today. Shade tomorrow, your children enjoy.",
            "Small sips daily. Mighty cups yearly. The way of the SIP, this is.",
            "The best plan, a boring one it is. Flashy, the losing one is.",
            "Forecast the market, no one can. Prepare for it, everyone should.",
        ]
        return _render(
            request,
            "step_plan_loading.html",
            {
                "current_step": 4,
                "session": session,
                "error": session.plan_error,
                "wisdom": random.choice(wisdoms),
            },
        )

    from apps.web.rendering import (
        chart_data_corpus,
        chart_data_donut,
        format_inr,
        render_markdown,
        short_fund_name,
    )

    response = _render(
        request,
        "step_result.html",
        {
            "current_step": 4,
            "session": session,
            "plan": session.plan,
            "profile": session.profile,
            "strategy": session.strategy,
            "format_inr": format_inr,
            "render_markdown": render_markdown,
            "chart_data_donut": chart_data_donut,
            "chart_data_corpus": chart_data_corpus,
            "short_fund_name": short_fund_name,
        },
    )
    return response
