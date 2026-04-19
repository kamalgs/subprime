"""HTMX API endpoints for the wizard web app."""

import re
from typing import Annotated

import asyncio
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Cookie, Form, Request, Response

logger = logging.getLogger(__name__)


def _multi_perspective_enabled() -> bool:
    """Feature gate for premium multi-perspective plan generation.

    Disabled by default while we stabilise. Set SUBPRIME_MULTI_PERSPECTIVE=1
    to re-enable the 3-perspective + evaluator + refiner flow. When disabled
    every plan is generated via the single-perspective 'basic' path,
    regardless of session.mode.
    """
    return os.environ.get("SUBPRIME_MULTI_PERSPECTIVE", "").strip().lower() in ("1", "true", "on", "yes")


def _refine_enabled() -> bool:
    """Feature gate for the senior-advisor refine pass.

    Disabled by default — doubles plan-gen latency (second full LLM call)
    and occasionally hangs on structured-output validation. Set
    SUBPRIME_REFINE=1 to re-enable.
    """
    return os.environ.get("SUBPRIME_REFINE", "").strip().lower() in ("1", "true", "on", "yes")


# Bound concurrent plan generations so a burst of requests can't pile up
# multiple 108K-token prompts + agent loops and starve the event loop.
# Value 2 gives some headroom; override via SUBPRIME_MAX_CONCURRENT_PLANS.
_PLAN_SEMAPHORE: asyncio.Semaphore | None = None


def _plan_semaphore() -> asyncio.Semaphore:
    global _PLAN_SEMAPHORE
    if _PLAN_SEMAPHORE is None:
        limit = int(os.environ.get("SUBPRIME_MAX_CONCURRENT_PLANS", "2") or "2")
        _PLAN_SEMAPHORE = asyncio.Semaphore(limit)
    return _PLAN_SEMAPHORE

from subprime.evaluation.personas import get_persona
from apps.web.session import Session
from subprime.core.config import ADVISOR_MODEL, REFINE_MODEL
from subprime.core.models import InvestorProfile, ConversationTurn
from subprime.advisor.planner import generate_plan, generate_strategy
from apps.web.rendering import chart_data_donut, render_markdown
from subprime.core.db import get_pool
from subprime.core.otp import create_otp, verify_otp, daily_otp_count

router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# GET /api/cost-estimate
# ---------------------------------------------------------------------------


@router.get("/cost-estimate")
async def api_cost_estimate(
    request: Request,
    benji_session: str | None = Cookie(default=None),
):
    """Return estimated cost (USD + INR) for plan generation in the current session.

    Used by the frontend to show users what a plan generation will cost before
    they commit, enabling a pay-per-use / micropayment flow.
    """
    from subprime.core.config import ADVISOR_MODEL
    from subprime.experiments.estimator import estimate_plan_cost

    store = request.app.state.session_store
    session = await _get_or_create_session(request, benji_session)

    mode = session.mode or "basic"
    est = estimate_plan_cost(
        mode=mode,
        model=ADVISOR_MODEL,
        n_perspectives=3,
    )

    return {
        "mode": est.mode,
        "n_advisor_calls": est.n_advisor_calls,
        "estimated_input_tokens": est.estimated_input_tokens,
        "estimated_output_tokens": est.estimated_output_tokens,
        "estimated_cost_usd": round(est.estimated_cost_usd, 5),
        "estimated_cost_inr": round(est.estimated_cost_inr, 3),
        "model": est.model,
    }

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
    benji_session: str | None = Cookie(default=None),
) -> Response:
    """Save tier selection and redirect to step 2."""
    store = request.app.state.session_store
    session = await _get_or_create_session(request, benji_session)
    session.mode = mode  # type: ignore[assignment]
    session.current_step = 2
    await store.save(session)

    response.status_code = 200
    response.headers["HX-Redirect"] = "/step/2"
    response.set_cookie("benji_session", session.id, httponly=True, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# POST /api/select-persona
# ---------------------------------------------------------------------------


@router.post("/select-persona")
async def select_persona(
    request: Request,
    response: Response,
    persona_id: Annotated[str, Form()],
    benji_session: str | None = Cookie(default=None),
) -> Response:
    """Load a preset persona and redirect to step 3."""
    store = request.app.state.session_store
    session = await _get_or_create_session(request, benji_session)
    profile = get_persona(persona_id)
    session.profile = profile
    session.current_step = 3
    await store.save(session)

    response.status_code = 200
    response.headers["HX-Redirect"] = "/step/3"
    response.set_cookie("benji_session", session.id, httponly=True, samesite="lax")
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
    benji_session: str | None = Cookie(default=None),
) -> Response:
    """Build a custom InvestorProfile from form data and redirect to step 3."""
    store = request.app.state.session_store
    session = await _get_or_create_session(request, benji_session)

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
    response.set_cookie("benji_session", session.id, httponly=True, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# GET /api/generate-strategy
# ---------------------------------------------------------------------------


@router.get("/generate-strategy")
async def api_generate_strategy(
    request: Request,
    benji_session: str | None = Cookie(default=None),
):
    """Generate a strategy for the current session and return the dashboard partial."""
    store = request.app.state.session_store
    session = await _get_or_create_session(request, benji_session)
    if session.profile is None:
        return Response(status_code=400, content="No profile in session")

    strategy, _ = await generate_strategy(session.profile, model=ADVISOR_MODEL)
    session.strategy = strategy
    await store.save(session)

    chart_data = chart_data_donut(
        strategy.equity_pct,
        strategy.debt_pct,
        strategy.gold_pct,
        strategy.other_pct,
        equity_sub=strategy.equity_sub,
        debt_sub=strategy.debt_sub,
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/strategy_dashboard.html",
        {"session": session, "strategy": strategy, "chart_data": chart_data, "render_markdown": render_markdown},
    )


# ---------------------------------------------------------------------------
# POST /api/revise-strategy
# ---------------------------------------------------------------------------


async def _revise_and_render(
    request: Request,
    feedback: str,
    benji_session: str | None,
    *,
    track_in_chat: bool,
):
    """Shared handler: revise strategy + re-render the dashboard partial.

    Set ``track_in_chat=False`` for silent revisions (e.g. answering open
    questions) — they should not appear in the free-form chat log.
    """
    store = request.app.state.session_store
    session = await _get_or_create_session(request, benji_session)
    if session.profile is None:
        return Response(status_code=400, content="No profile in session")

    if track_in_chat:
        session.strategy_chat.append(ConversationTurn(role="user", content=feedback))

    strategy, _ = await generate_strategy(
        session.profile,
        feedback=feedback,
        current_strategy=session.strategy,
        model=ADVISOR_MODEL,
    )
    session.strategy = strategy

    if track_in_chat:
        session.strategy_chat.append(
            ConversationTurn(role="advisor", content="Strategy updated based on your feedback.")
        )
    await store.save(session)

    chart_data = chart_data_donut(
        strategy.equity_pct,
        strategy.debt_pct,
        strategy.gold_pct,
        strategy.other_pct,
        equity_sub=strategy.equity_sub,
        debt_sub=strategy.debt_sub,
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/strategy_dashboard.html",
        {"session": session, "strategy": strategy, "chart_data": chart_data, "render_markdown": render_markdown},
    )


@router.post("/revise-strategy")
async def api_revise_strategy(
    request: Request,
    feedback: Annotated[str, Form()],
    benji_session: str | None = Cookie(default=None),
):
    """Revise strategy via free-form chat (appears in the chat log)."""
    return await _revise_and_render(request, feedback, benji_session, track_in_chat=True)


@router.post("/answer-questions")
async def api_answer_questions(
    request: Request,
    feedback: Annotated[str, Form()],
    benji_session: str | None = Cookie(default=None),
):
    """Silently revise strategy using answers to the open questions.

    Does NOT append to the strategy chat log — open-questions and the chat
    are independent input channels from the user's point of view.
    """
    return await _revise_and_render(request, feedback, benji_session, track_in_chat=False)


# ---------------------------------------------------------------------------
# POST /api/generate-plan
# ---------------------------------------------------------------------------


async def _generate_plan_task(app, session_id: str) -> None:
    """Runs in the background — generate the plan, save it to the session."""
    import time as _time
    store = app.state.session_store
    session = await store.get(session_id)
    if session is None or session.profile is None:
        logger.warning("[plan %s] skipped — no session/profile", session_id[:8])
        return

    effective_mode = session.mode if _multi_perspective_enabled() else "basic"
    sem = _plan_semaphore()
    logger.info(
        "[plan %s] START mode=%s multi=%s sem_avail=%s model=%s persona=%s has_strategy=%s",
        session_id[:8], effective_mode, _multi_perspective_enabled(),
        sem._value if hasattr(sem, '_value') else '?',
        ADVISOR_MODEL, session.profile.id if session.profile else "?",
        session.strategy is not None,
    )
    t0 = _time.time()
    refine_model = REFINE_MODEL if _refine_enabled() else None
    try:
        async with sem:
            plan, usage = await generate_plan(
                session.profile,
                strategy=session.strategy,
                mode=effective_mode,
                n_perspectives=3,
                model=ADVISOR_MODEL,
                refine_model=refine_model,
            )
        dt = _time.time() - t0
        logger.info(
            "[plan %s] DONE in %.1fs — allocations=%d returns=%s tokens=(in=%s,out=%s)",
            session_id[:8], dt, len(plan.allocations), plan.projected_returns,
            getattr(usage, "input_tokens", "?"),
            getattr(usage, "output_tokens", "?"),
        )

        # Re-fetch in case another request updated it concurrently.
        session = await store.get(session_id) or session
        session.plan = plan
        session.plan_generating = False
        session.plan_error = None
        session.current_step = 4
        await store.save(session)
        logger.info("[plan %s] SAVED", session_id[:8])

        from subprime.core.conversations import save_conversation
        from subprime.core.db import get_pool as _get_pool
        await save_conversation(session=session, pool=_get_pool())
    except Exception as exc:
        dt = _time.time() - t0
        logger.exception(
            "[plan %s] FAILED after %.1fs: %s", session_id[:8], dt, exc,
        )
        session = await store.get(session_id) or session
        session.plan_generating = False
        session.plan_error = str(exc)[:200]
        await store.save(session)


@router.get("/plan-status")
async def api_plan_status(
    request: Request,
    benji_session: str | None = Cookie(default=None),
):
    """JSON status for the loading screen poller."""
    from fastapi.responses import JSONResponse
    store = request.app.state.session_store
    if not benji_session:
        return JSONResponse({"ready": False, "error": "no-session"})
    session = await store.get(benji_session)
    if not session:
        return JSONResponse({"ready": False, "error": "no-session"})
    return JSONResponse({
        "ready": session.plan is not None,
        "generating": session.plan_generating,
        "error": session.plan_error,
    })


@router.post("/generate-plan")
async def api_generate_plan(
    request: Request,
    background: BackgroundTasks,
    benji_session: str | None = Cookie(default=None),
) -> Response:
    """Plain HTML-form POST: kick off plan generation in the background and
    redirect (HTTP 303) to /step/4. Browser follows the redirect natively —
    no HTMX, no JS."""
    from fastapi.responses import RedirectResponse

    store = request.app.state.session_store
    session = await _get_or_create_session(request, benji_session)
    if session.profile is None:
        return Response(status_code=400, content="No profile in session")

    session.plan = None
    session.plan_generating = True
    session.plan_error = None
    session.current_step = 4
    await store.save(session)

    logger.info(
        "[plan %s] QUEUED mode=%s profile=%s",
        session.id[:8], session.mode,
        session.profile.id if session.profile else "?",
    )

    background.add_task(_generate_plan_task, request.app, session.id)

    # 303 See Other: browser does a GET on /step/4 even after a POST.
    resp = RedirectResponse(url="/step/4", status_code=303)
    resp.set_cookie("benji_session", session.id, httponly=True, samesite="lax")
    return resp


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
    response.set_cookie("benji_session", new_session.id, httponly=True, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# POST /api/request-otp
# ---------------------------------------------------------------------------


@router.post("/request-otp")
async def api_request_otp(
    request: Request,
    email: Annotated[str | None, Form()] = None,
    benji_session: str | None = Cookie(default=None),
):
    """Generate and email an OTP for premium access."""
    templates = request.app.state.templates
    pool = get_pool()

    if not pool:
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": "Premium is not available right now — please try the Basic plan.",
            "show_retry": False, "email": email,
        })

    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": "Please enter a valid email address.",
            "show_retry": True, "email": email,
        })

    result = await create_otp(pool, email.strip().lower())
    if not result["success"]:
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": result["reason"], "show_retry": False, "email": email,
        })

    from apps.web.email import send_otp_email
    sent = await send_otp_email(email.strip().lower(), result["code"])
    if not sent:
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": "Could not send email — please check your address and try again.",
            "show_retry": True, "email": email,
        })

    return templates.TemplateResponse(request, "partials/otp_verify.html", {
        "email": email.strip().lower(),
    })


# ---------------------------------------------------------------------------
# POST /api/verify-otp
# ---------------------------------------------------------------------------


@router.post("/verify-otp")
async def api_verify_otp(
    request: Request,
    email: Annotated[str, Form()],
    code: Annotated[str, Form()],
    benji_session: str | None = Cookie(default=None),
):
    """Verify an OTP and grant premium access."""
    import os
    templates = request.app.state.templates
    pool = get_pool()

    cheat = os.environ.get("SUBPRIME_OTP_CHEAT", "").strip()
    is_cheat = bool(cheat) and code.strip() == cheat

    if not pool and not is_cheat:
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": "Premium is not available right now.",
            "show_retry": False, "email": email,
        })

    store = request.app.state.session_store
    session = await _get_or_create_session(request, benji_session)

    verified = is_cheat or await verify_otp(pool, email.strip().lower(), code.strip())
    if not verified:
        return templates.TemplateResponse(request, "partials/otp_error.html", {
            "message": "Invalid or expired code. Please request a new one.",
            "show_retry": True, "email": email,
        })

    session.mode = "premium"
    session.current_step = 2
    if is_cheat:
        session.is_demo = True
    await store.save(session)

    response = Response(status_code=200)
    response.headers["HX-Redirect"] = "/step/2"
    response.set_cookie("benji_session", session.id, httponly=True, samesite="lax")
    return response
