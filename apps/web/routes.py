"""Page routes for the wizard web app."""

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from apps.web._personas import load_personas, get_persona  # noqa: F401
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
    context["request"] = request
    return templates.TemplateResponse(template_name, context)


# ---------------------------------------------------------------------------
# Step 1 — Choose Plan
# ---------------------------------------------------------------------------


@router.get("/step/1", response_class=HTMLResponse)
async def step1(
    request: Request,
    finadvisor_session: str | None = Cookie(default=None),
) -> HTMLResponse:
    session, session_id = await _get_or_create_session(request, finadvisor_session)
    response = _render(request, "step_plan.html", {"current_step": 1, "session": session})
    response.set_cookie("finadvisor_session", session_id, httponly=True, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# Step 2 — Your Profile
# ---------------------------------------------------------------------------


@router.get("/step/2", response_class=HTMLResponse)
async def step2(
    request: Request,
    finadvisor_session: str | None = Cookie(default=None),
) -> HTMLResponse:
    if not finadvisor_session:
        return RedirectResponse(url="/step/1", status_code=302)
    store = request.app.state.session_store
    session = await store.get(finadvisor_session)
    if not session:
        return RedirectResponse(url="/step/1", status_code=302)

    personas = load_personas()
    response = _render(
        request,
        "step_profile.html",
        {"current_step": 2, "session": session, "personas": personas},
    )
    return response


# ---------------------------------------------------------------------------
# Step 3 — Strategy
# ---------------------------------------------------------------------------


@router.get("/step/3", response_class=HTMLResponse)
async def step3(
    request: Request,
    finadvisor_session: str | None = Cookie(default=None),
) -> HTMLResponse:
    if not finadvisor_session:
        return RedirectResponse(url="/step/1", status_code=302)
    store = request.app.state.session_store
    session = await store.get(finadvisor_session)
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
    finadvisor_session: str | None = Cookie(default=None),
) -> HTMLResponse:
    if not finadvisor_session:
        return RedirectResponse(url="/step/1", status_code=302)
    store = request.app.state.session_store
    session = await store.get(finadvisor_session)
    if not session or session.plan is None:
        return RedirectResponse(url="/step/1", status_code=302)

    response = _render(
        request,
        "step_result.html",
        {"current_step": 4, "session": session},
    )
    return response
