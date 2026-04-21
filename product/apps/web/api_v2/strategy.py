"""Strategy generation and revision."""
from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request
from opentelemetry import trace

from apps.web.api_v2._session import COOKIE_NAME, get_or_create
from apps.web.api_v2.dto import FeedbackBody, StrategyResponse
from subprime import observability as obs
from subprime.advisor.planner import generate_strategy
from subprime.core.config import ADVISOR_MODEL
from subprime.core.models import ConversationTurn

router = APIRouter()
_tracer = trace.get_tracer("subprime.web")


def _annotate_strategy_span(span, *, t0: float, usage, op: str) -> None:
    dt = time.time() - t0
    in_tok = getattr(usage, "input_tokens", 0) or 0
    cache_r = getattr(usage, "cache_read_tokens", 0) or 0
    span.set_attribute(obs.ELAPSED_S, dt)
    span.set_attribute(obs.INPUT_TOKENS, in_tok)
    span.set_attribute(obs.OUTPUT_TOKENS, getattr(usage, "output_tokens", 0) or 0)
    span.set_attribute(obs.CACHE_READ_TOKENS, cache_r)
    span.set_attribute(obs.CACHE_WRITE_TOKENS, getattr(usage, "cache_write_tokens", 0) or 0)
    if cache_r + in_tok > 0:
        span.set_attribute(obs.CACHE_HIT_RATIO, cache_r / (cache_r + in_tok))
    span.set_status(trace.Status(trace.StatusCode.OK))
    obs.strategy_duration.record(dt, {"op": op, "model": ADVISOR_MODEL})
    obs.strategy_total.add(1, {"op": op, "status": "success"})
    obs.record_llm_usage(usage, model=ADVISOR_MODEL, op="strategy")


@router.post("/strategy/generate")
async def generate(
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> StrategyResponse:
    """Run the strategy advisor against the session profile. Returns JSON."""
    s = await get_or_create(request, benji_session)
    if s.profile is None:
        raise HTTPException(400, "No profile on session — complete step 2 first.")

    attrs = {obs.SESSION_ID: s.id, obs.PERSONA_ID: s.profile.id,
             obs.ADVISOR_MODEL: ADVISOR_MODEL}
    with _tracer.start_as_current_span("subprime.strategy.generate", attributes=attrs) as span:
        t0 = time.time()
        strategy, usage = await generate_strategy(s.profile, model=ADVISOR_MODEL)
        _annotate_strategy_span(span, t0=t0, usage=usage, op="generate")
    s.strategy = strategy
    if s.current_step < 3:
        s.current_step = 3
    await request.app.state.session_store.save(s)
    return StrategyResponse(
        strategy=strategy,
        chat=[t.model_dump() for t in s.strategy_chat],
    )


@router.post("/strategy/revise")
async def revise(
    body: FeedbackBody,
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> StrategyResponse:
    """Free-form chat revision — adds to the chat log."""
    s = await get_or_create(request, benji_session)
    if s.profile is None:
        raise HTTPException(400, "No profile on session.")
    s.strategy_chat.append(ConversationTurn(role="user", content=body.feedback))
    attrs = {obs.SESSION_ID: s.id, obs.PERSONA_ID: s.profile.id,
             obs.ADVISOR_MODEL: ADVISOR_MODEL}
    with _tracer.start_as_current_span("subprime.strategy.revise", attributes=attrs) as span:
        t0 = time.time()
        strategy, usage = await generate_strategy(
            s.profile,
            feedback=body.feedback,
            current_strategy=s.strategy,
            model=ADVISOR_MODEL,
        )
        _annotate_strategy_span(span, t0=t0, usage=usage, op="revise")
    s.strategy = strategy
    s.strategy_chat.append(
        ConversationTurn(role="advisor", content="Strategy updated based on your feedback.")
    )
    await request.app.state.session_store.save(s)
    return StrategyResponse(
        strategy=strategy,
        chat=[t.model_dump() for t in s.strategy_chat],
    )


@router.post("/strategy/answer-questions")
async def answer_questions(
    body: FeedbackBody,
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> StrategyResponse:
    """Silently refine the strategy using answers to open questions.

    Separate from revise so it does NOT appear in the free-form chat log.
    """
    s = await get_or_create(request, benji_session)
    if s.profile is None:
        raise HTTPException(400, "No profile on session.")
    attrs = {obs.SESSION_ID: s.id, obs.PERSONA_ID: s.profile.id,
             obs.ADVISOR_MODEL: ADVISOR_MODEL}
    with _tracer.start_as_current_span("subprime.strategy.answer_questions", attributes=attrs) as span:
        t0 = time.time()
        strategy, usage = await generate_strategy(
            s.profile,
            feedback=body.feedback,
            current_strategy=s.strategy,
            model=ADVISOR_MODEL,
        )
        _annotate_strategy_span(span, t0=t0, usage=usage, op="answer_questions")
    s.strategy = strategy
    await request.app.state.session_store.save(s)
    return StrategyResponse(
        strategy=strategy,
        chat=[t.model_dump() for t in s.strategy_chat],
    )
