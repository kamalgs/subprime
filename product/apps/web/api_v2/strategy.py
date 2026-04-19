"""Strategy generation and revision."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request

from apps.web.api_v2._session import COOKIE_NAME, get_or_create
from apps.web.api_v2.dto import FeedbackBody, StrategyResponse
from subprime.advisor.planner import generate_strategy
from subprime.core.config import ADVISOR_MODEL
from subprime.core.models import ConversationTurn

router = APIRouter()


@router.post("/strategy/generate")
async def generate(
    request: Request,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> StrategyResponse:
    """Run the strategy advisor against the session profile. Returns JSON."""
    s = await get_or_create(request, benji_session)
    if s.profile is None:
        raise HTTPException(400, "No profile on session — complete step 2 first.")

    strategy, _ = await generate_strategy(s.profile, model=ADVISOR_MODEL)
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
    strategy, _ = await generate_strategy(
        s.profile,
        feedback=body.feedback,
        current_strategy=s.strategy,
        model=ADVISOR_MODEL,
    )
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
    strategy, _ = await generate_strategy(
        s.profile,
        feedback=body.feedback,
        current_strategy=s.strategy,
        model=ADVISOR_MODEL,
    )
    s.strategy = strategy
    await request.app.state.session_store.save(s)
    return StrategyResponse(
        strategy=strategy,
        chat=[t.model_dump() for t in s.strategy_chat],
    )
