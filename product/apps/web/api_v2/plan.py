"""Plan generation — kicks off a background task and exposes a status poller."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException, Request, status

from opentelemetry import trace

from apps.web.api_v2._session import COOKIE_NAME, get_or_create
from apps.web.api_v2.dto import AckResponse, PlanResponse, PlanStatusResponse
from subprime import observability as obs
from subprime.advisor.planner import generate_plan_staged
from subprime.core.config import ADVISOR_MODEL, ADVISOR_MODEL_BASIC, REFINE_MODEL

_tracer = trace.get_tracer("subprime.web")

logger = logging.getLogger(__name__)
router = APIRouter()


def _multi_perspective_enabled() -> bool:
    return os.environ.get("SUBPRIME_MULTI_PERSPECTIVE", "").strip().lower() in (
        "1",
        "true",
        "on",
        "yes",
    )


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
    # Tier is still used to pick the advisor model + shape the universe context;
    # multi-perspective is off for both tiers now.
    tier = s.mode if s.mode in ("basic", "premium") else "basic"
    slim_universe = tier == "basic"
    effective_mode = "basic"
    refine_model = REFINE_MODEL if _refine_enabled() else None
    # Basic tier routes to a smaller model through AI Gateway so repeat
    # archetype selections hit cache and premium traffic still gets the
    # larger model.
    active_model = ADVISOR_MODEL_BASIC if tier == "basic" and ADVISOR_MODEL_BASIC else ADVISOR_MODEL
    logger.info(
        "[plan %s] START mode=%s multi=%s refine=%s model=%s persona=%s has_strategy=%s",
        session_id[:8],
        effective_mode,
        _multi_perspective_enabled(),
        bool(refine_model),
        active_model,
        s.profile.id if s.profile else "?",
        s.strategy is not None,
    )
    t0 = time.time()
    span_attrs = {
        obs.SESSION_ID: session_id,
        obs.PERSONA_ID: s.profile.id,
        obs.TIER: tier,
        obs.ADVISOR_MODEL: active_model,
    }
    if refine_model:
        span_attrs[obs.REFINE_MODEL] = refine_model
    with _tracer.start_as_current_span("subprime.plan.generate", attributes=span_attrs) as span:
        try:

            async def on_partial(partial_plan, stages_done):
                # Persist each stage to the session so the UI can render as
                # sections arrive. Re-fetch in case a parallel request touched
                # the session, then write only the plan-specific fields.
                try:
                    from apps.web.api_v2._format import format_plan_prose

                    format_plan_prose(partial_plan)
                except Exception:
                    logger.warning("format_plan_prose failed on partial", exc_info=True)
                cur = await store.get(session_id) or s
                cur.plan = partial_plan
                cur.plan_stages = list(stages_done)
                cur.plan_generating = "setup" not in stages_done or "risks" not in stages_done
                cur.plan_error = None
                if "core" in stages_done and cur.current_step < 4:
                    cur.current_step = 4
                await store.save(cur)
                logger.info(
                    "[plan %s] stage %s persisted (stages=%s)",
                    session_id[:8],
                    stages_done[-1] if stages_done else "?",
                    stages_done,
                )

            async with _plan_semaphore():
                plan, usage = await generate_plan_staged(
                    s.profile,
                    s.strategy,
                    model=active_model,
                    slim_universe=slim_universe,
                    on_partial=on_partial,
                )
            dt = time.time() - t0
            in_tok = getattr(usage, "input_tokens", 0) or 0
            out_tok = getattr(usage, "output_tokens", 0) or 0
            cache_r = getattr(usage, "cache_read_tokens", 0) or 0
            cache_w = getattr(usage, "cache_write_tokens", 0) or 0
            span.set_attribute(obs.ELAPSED_S, dt)
            span.set_attribute(obs.INPUT_TOKENS, in_tok)
            span.set_attribute(obs.OUTPUT_TOKENS, out_tok)
            span.set_attribute(obs.CACHE_READ_TOKENS, cache_r)
            span.set_attribute(obs.CACHE_WRITE_TOKENS, cache_w)
            span.set_attribute(obs.REQUESTS, getattr(usage, "requests", 0) or 0)
            span.set_attribute(obs.TOOL_CALLS, getattr(usage, "tool_calls", 0) or 0)
            denom = cache_r + in_tok
            if denom > 0:
                span.set_attribute(obs.CACHE_HIT_RATIO, cache_r / denom)
            span.set_status(trace.Status(trace.StatusCode.OK))
            obs.plan_duration.record(dt, {"tier": tier, "model": active_model})
            obs.plan_total.add(1, {"tier": tier, "status": "success"})
            obs.record_llm_usage(usage, model=active_model, op="plan")
            logger.info(
                "[plan %s] DONE in %.1fs — allocations=%d tokens=(in=%s,out=%s,cache_r=%s,cache_w=%s)",
                session_id[:8],
                dt,
                len(plan.allocations),
                in_tok,
                out_tok,
                cache_r,
                cache_w,
            )

            # Final formatting pass on the fully-populated plan.
            from apps.web.api_v2._format import format_plan_prose

            format_plan_prose(plan)

            s = await store.get(session_id) or s
            s.plan = plan
            s.plan_stages = ["core", "risks", "setup"]
            s.plan_generating = False
            s.plan_error = None
            s.current_step = 4
            await store.save(s)

            from subprime.core.conversations import save_conversation
            from subprime.core.db import get_pool

            await save_conversation(session=s, pool=get_pool())
        except Exception as exc:
            dt = time.time() - t0
            span.set_attribute(obs.ELAPSED_S, dt)
            span.record_exception(exc)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)[:200]))
            obs.plan_total.add(1, {"tier": tier, "status": "error"})
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
    s.plan_stages = []
    s.plan_generating = True
    s.plan_error = None
    s.current_step = 4
    await request.app.state.session_store.save(s)
    logger.info(
        "[plan %s] QUEUED mode=%s persona=%s", s.id[:8], s.mode, s.profile.id if s.profile else "?"
    )
    background.add_task(_run_plan_task, request.app, s.id)
    return AckResponse()


@router.get("/plan/status")
async def status_(
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> PlanStatusResponse:
    s = await get_or_create(request, benji_session)
    # "Ready" now means the core allocations are on the session — UI can
    # start rendering immediately. Remaining stages land via further polls.
    stages = list(s.plan_stages or [])
    return PlanStatusResponse(
        ready=s.plan is not None and "core" in stages,
        generating=s.plan_generating,
        error=s.plan_error,
        stages_done=stages,
    )


@router.get("/plan/stream")
async def stream_status(
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
):
    """Server-Sent Events stream of plan generation progress.

    Emits one ``event: stage`` per ``stages_done`` transition so the UI
    re-renders as soon as the server persists a stage — cuts perceived
    latency vs the 2-second /plan/status poll.
    """
    import json

    from fastapi.responses import StreamingResponse

    s = await get_or_create(request, benji_session)
    session_id = s.id
    store = request.app.state.session_store

    async def _event_gen():
        seen: list[str] = []
        # Tight-loop the session store. Each iteration is cheap (in-memory
        # or a single SELECT against Postgres) so 250ms is well inside any
        # sane latency budget and still sub-second for every stage landing.
        for _ in range(600):  # max ~2.5 minutes
            cur = await store.get(session_id)
            if cur is None:
                break
            stages = list(cur.plan_stages or [])
            if stages != seen:
                seen = stages
                payload = {
                    "stages_done": stages,
                    "ready": cur.plan is not None and "core" in stages,
                    "generating": cur.plan_generating,
                    "error": cur.plan_error,
                }
                yield f"event: stage\ndata: {json.dumps(payload)}\n\n"
            if not cur.plan_generating:
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # Caddy/nginx: don't buffer SSE
            "Connection": "keep-alive",
        },
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


def _safe_filename(profile_name: str, extension: str) -> str:
    """Slugify investor name for Content-Disposition filename."""
    import re

    slug = re.sub(r"[^A-Za-z0-9]+", "-", profile_name.strip()).strip("-") or "plan"
    date = __import__("datetime").datetime.utcnow().strftime("%Y%m%d")
    return f"benji-plan-{slug.lower()}-{date}.{extension}"


@router.get("/plan/download.pdf")
async def download_pdf(
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
):
    """Stream the current plan as a branded A4 PDF."""
    from fastapi.responses import Response
    from subprime.core.plan_report import build_plan_pdf

    s = await get_or_create(request, benji_session)
    if s.plan is None or s.profile is None:
        raise HTTPException(404, "Plan not available.")
    pdf = await asyncio.to_thread(build_plan_pdf, s.plan, s.profile)
    filename = _safe_filename(s.profile.name, "pdf")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/plan/download.xlsx")
async def download_xlsx(
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
):
    """Stream the current plan as an Excel workbook."""
    from fastapi.responses import Response
    from subprime.core.plan_report import build_plan_xlsx

    s = await get_or_create(request, benji_session)
    if s.plan is None or s.profile is None:
        raise HTTPException(404, "Plan not available.")
    xlsx = await asyncio.to_thread(build_plan_xlsx, s.plan, s.profile)
    filename = _safe_filename(s.profile.name, "xlsx")
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
