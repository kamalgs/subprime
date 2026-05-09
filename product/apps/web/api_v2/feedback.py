"""POST /api/v2/feedback — NPS-style post-plan feedback.

Writes ``conversations.feedback`` JSONB for the latest conversation row
attached to the current session. Idempotent: a second POST replaces the
prior value. Returns 409 when no conversation exists yet (the user
hasn't reached the plan stage that triggers conversation persistence).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response

from apps.web.api_v2._session import COOKIE_NAME, get_or_create, set_cookie
from apps.web.api_v2.dto import AckResponse, SessionFeedbackBody
from subprime.core.db import get_pool
from subprime.feedback import upsert_feedback

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/feedback")
async def post_feedback(
    body: SessionFeedbackBody,
    request: Request,
    response: Response,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> AckResponse:
    pool = get_pool()
    if pool is None:
        raise HTTPException(503, "Feedback capture unavailable.")

    s = await get_or_create(request, benji_session)
    set_cookie(response, s.id)

    try:
        updated = await upsert_feedback(
            pool,
            s.id,
            nps=body.nps,
            actionable=body.actionable,
            free_text=body.free_text,
        )
    except Exception:
        logger.exception("feedback: write failed for session=%s", s.id)
        raise HTTPException(500, "Could not save feedback.")

    if not updated:
        raise HTTPException(
            409,
            "No conversation exists for this session yet. "
            "Generate a plan before submitting feedback.",
        )
    return AckResponse(ok=True)
