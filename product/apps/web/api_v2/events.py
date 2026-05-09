"""POST /api/v2/events — bulk-stage client UX events.

The SPA buffers events client-side and POSTs in batches (max 50). The
endpoint stamps ``session_id`` from the cookie and bulk-inserts in a
single transaction so we never end up with half-applied batches.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response

from apps.web.api_v2._session import COOKIE_NAME, get_or_create, set_cookie
from apps.web.api_v2.dto import EventsAccepted, EventsBody
from subprime.core.db import get_pool
from subprime.feedback import insert_events

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/events")
async def post_events(
    body: EventsBody,
    request: Request,
    response: Response,
    benji_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> EventsAccepted:
    """Stage one batch of UX events. Atomic: all rows insert or none do."""
    pool = get_pool()
    if pool is None:
        # Without a Postgres pool we have nowhere to put these. Surface
        # 503 rather than silently dropping — the client can retry once
        # the backend is healthy.
        raise HTTPException(503, "Event capture unavailable.")

    s = await get_or_create(request, benji_session)
    set_cookie(response, s.id)

    pairs = [(e.kind, e.payload) for e in body.events]
    try:
        accepted = await insert_events(pool, s.id, pairs)
    except Exception:
        logger.exception("events: bulk insert failed for session=%s", s.id)
        raise HTTPException(500, "Could not stage events.")
    return EventsAccepted(accepted=accepted)
