"""Admin endpoints — feature flag CRUD.

Auth: a fixed bearer token from SUBPRIME_ADMIN_TOKEN. Intentionally simple;
this isn't a multi-tenant app. When the token isn't set, the endpoints
return 503 — safer than exposing them unauthenticated.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from subprime.core.db import get_pool
from subprime.feedback import fetch_session_events
from subprime.flags import delete_flag, list_flags, set_flag

router = APIRouter(prefix="/admin")


def _require_admin(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    token = os.environ.get("SUBPRIME_ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(503, "Admin API disabled (SUBPRIME_ADMIN_TOKEN not set).")
    expected = f"Bearer {token}"
    if authorization != expected:
        raise HTTPException(401, "Invalid admin token.")


class FlagBody(BaseModel):
    definition: dict
    description: str = ""


@router.get("/flags", dependencies=[Depends(_require_admin)])
async def get_flags() -> list[dict]:
    return await list_flags()


@router.put("/flags/{key}", dependencies=[Depends(_require_admin)])
async def put_flag(key: str, body: FlagBody) -> dict:
    await set_flag(key, definition=body.definition, description=body.description)
    return {"key": key, "ok": True}


@router.delete("/flags/{key}", dependencies=[Depends(_require_admin)])
async def remove_flag(key: str) -> dict:
    removed = await delete_flag(key)
    return {"key": key, "removed": removed}


@router.get("/sessions/{session_id}/events", dependencies=[Depends(_require_admin)])
async def get_session_events(session_id: str) -> dict:
    """List staged session events. Test-harness + ad-hoc debugging only."""
    pool = get_pool()
    if pool is None:
        raise HTTPException(503, "Event store unavailable (no DB).")
    events = await fetch_session_events(pool, session_id)
    return {"session_id": session_id, "events": events}
