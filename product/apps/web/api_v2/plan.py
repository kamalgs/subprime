"""Plan generation — kicks off a background task and exposes a status poller."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException, Request, status

from apps.web.api_v2._session import COOKIE_NAME, get_or_create
from apps.web.api_v2.dto import AckResponse, PlanResponse, PlanStatusResponse
from subprime.advisor.planner import generate_plan
from subprime.core.config import ADVISOR_MODEL, REFINE_MODEL

logger = logging.getLogger(__name__)
router = APIRouter()


def _multi_perspective_enabled() -> bool:
    return os.environ.get("SUBPRIME_MULTI_PERSPECTIVE", "").strip().lower() in ("1", "true", "on", "yes")


def _refine_enabled() -> bool:
    return os.environ.get("SUBPRIME_REFINE", "").strip().lower() in ("1", "true", "on", "yes")


# Bound concurrent plan generations. Default 2.
_PLAN_SEMAPHORE: asyncio.Semaphore | None = None


def _plan_semaphore() -> asyncio.Semaphore:
    global _PLAN_SEMAPHORE
    if _PLAN_SEMAPHORE is None:
        limit = int(os.environ.get("SUBPRIME_MAX_CONCURRENT_PLANS", "2") or "2")
        _PLAN_SEMAPHORE = asyncio.Semaphore(limit)
    return _PLAN_SEMAPHORE


async def _run_plan_task(app, session_id: str) -> None:
    """Background task: generate plan and persist to the session."""
    store = app.state.session_store
    s = await store.get(session_id)
    if s is None or s.profile is None:
        return
    effective_mode = s.mode if _multi_perspective_enabled() else "basic"
    refine_model = REFINE_MODEL if _refine_enabled() else None
    logger.info(
        "[plan %s] START mode=%s multi=%s refine=%s model=%s persona=%s has_strategy=%s",
        session_id[:8], effective_mode, _multi_perspective_enabled(),
        bool(refine_model), ADVISOR_MODEL,
        s.profile.id if s.profile else "?", s.strategy is not None,
    )
    t0 = time.time()
    try:
        async with _plan_semaphore():
            plan, usage = await generate_plan(
                s.profile,
                strategy=s.strategy,
                mode=effective_mode,
                n_perspectives=3,
                model=ADVISOR_MODEL,
                refine_model=refine_model,
            )
        dt = time.time() - t0
        logger.info(
            "[plan %s] DONE in %.1fs — allocations=%d tokens=(in=%s,out=%s)",
            session_id[:8], dt, len(plan.allocations),
            getattr(usage, "input_tokens", "?"),
            getattr(usage, "output_tokens", "?"),
        )
        s = await store.get(session_id) or s
        s.plan = plan
        s.plan_generating = False
        s.plan_error = None
        s.current_step = 4
        await store.save(s)

        from subprime.core.conversations import save_conversation
        from subprime.core.db import get_pool
        await save_conversation(session=s, pool=get_pool())
    except Exception as exc:
        dt = time.time() - t0
        logger.exception("[plan %s] FAILED after %.1fs", session_id[:8], dt)
        s = await store.get(session_id) or s
        s.plan_generating = False
        s.plan_error = str(exc)[:200]
        await store.save(s)


@router.post("/plan/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate(
    request: Request,
    background: BackgroundTasks,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> AckResponse:
    """Enqueue a plan generation. Returns immediately (202); poll /plan/status."""
    s = await get_or_create(request, benji_session)
    if s.profile is None:
        raise HTTPException(400, "No profile on session.")
    s.plan = None
    s.plan_generating = True
    s.plan_error = None
    s.current_step = 4
    await request.app.state.session_store.save(s)
    logger.info("[plan %s] QUEUED mode=%s persona=%s",
                s.id[:8], s.mode, s.profile.id if s.profile else "?")
    background.add_task(_run_plan_task, request.app, s.id)
    return AckResponse()


@router.get("/plan/status")
async def status_(
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> PlanStatusResponse:
    s = await get_or_create(request, benji_session)
    return PlanStatusResponse(
        ready=s.plan is not None,
        generating=s.plan_generating,
        error=s.plan_error,
    )


@router.get("/plan")
async def get_plan(
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> PlanResponse:
    """Return the stored plan. 404 if not ready yet."""
    s = await get_or_create(request, benji_session)
    if s.plan is None or s.profile is None:
        raise HTTPException(404, "Plan not available.")
    return PlanResponse(plan=s.plan, profile=s.profile, strategy=s.strategy)
