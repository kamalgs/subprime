"""Internal session helpers used by every v2 endpoint."""
from __future__ import annotations

from fastapi import Cookie, Request, Response

from subprime.core.models import Session

COOKIE_NAME = "benji_session"


async def get_or_create(
    request: Request,
    session_id: str | None,
) -> Session:
    store = request.app.state.session_store
    if session_id:
        existing = await store.get(session_id)
        if existing is not None:
            return existing
    s = Session()
    await store.save(s)
    return s


def set_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        session_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,  # 1 week
    )


SessionCookie = Cookie(default=None, alias=COOKIE_NAME)
