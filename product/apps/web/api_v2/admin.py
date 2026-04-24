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
