"""Tests for POST /api/v2/feedback."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests._fake_pg import FakePool


@pytest.fixture
async def client_with_pool(monkeypatch):
    pool = FakePool()
    from subprime.core import db as _db

    monkeypatch.setattr(_db, "_pool", pool)

    from apps.web.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c, pool


async def _new_session(client: AsyncClient) -> str:
    r = await client.get("/api/v2/session")
    return r.json()["id"]


@pytest.mark.asyncio
async def test_feedback_writes_to_latest_conversation(client_with_pool):
    client, pool = client_with_pool
    sid = await _new_session(client)
    cid = pool.seed_conversation(sid)

    body = {"nps": 9, "actionable": "yes", "free_text": "Loved it."}
    r = await client.post("/api/v2/feedback", json=body)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    fb = pool.get_conversation(cid)["feedback"]
    assert fb is not None
    assert fb["nps"] == 9
    assert fb["actionable"] == "yes"
    assert fb["free_text"] == "Loved it."
    assert "submitted_at" in fb  # server-stamped


@pytest.mark.asyncio
async def test_feedback_idempotent_overwrites(client_with_pool):
    """Posting twice — second value wins, no extra rows."""
    client, pool = client_with_pool
    sid = await _new_session(client)
    cid = pool.seed_conversation(sid)

    await client.post(
        "/api/v2/feedback",
        json={"nps": 3, "actionable": "no", "free_text": "Meh"},
    )
    await client.post(
        "/api/v2/feedback",
        json={"nps": 8, "actionable": "mostly", "free_text": "Better now"},
    )

    fb = pool.get_conversation(cid)["feedback"]
    assert fb["nps"] == 8
    assert fb["actionable"] == "mostly"
    assert fb["free_text"] == "Better now"

    # Still only one conversation row for this session
    assert len([c for c in pool._db.conversations if c["session_id"] == sid]) == 1


@pytest.mark.asyncio
async def test_feedback_409_when_no_conversation(client_with_pool):
    client, _pool = client_with_pool
    await _new_session(client)
    r = await client.post(
        "/api/v2/feedback",
        json={"nps": 7, "actionable": "yes", "free_text": None},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_feedback_validates_nps_range(client_with_pool):
    client, pool = client_with_pool
    sid = await _new_session(client)
    pool.seed_conversation(sid)

    for bad in (-1, 11, 100):
        r = await client.post(
            "/api/v2/feedback",
            json={"nps": bad, "actionable": "yes", "free_text": None},
        )
        assert r.status_code == 422, bad


@pytest.mark.asyncio
async def test_feedback_validates_actionable_enum(client_with_pool):
    client, pool = client_with_pool
    sid = await _new_session(client)
    pool.seed_conversation(sid)

    r = await client.post(
        "/api/v2/feedback",
        json={"nps": 7, "actionable": "kind-of", "free_text": None},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_feedback_targets_latest_conversation(client_with_pool):
    """When a session has multiple conversation rows, only the most recent is updated."""
    client, pool = client_with_pool
    sid = await _new_session(client)
    older = pool.seed_conversation(sid)
    # Bump created_at on a second one to simulate a later run
    import time

    time.sleep(0.001)
    newer = pool.seed_conversation(sid)

    r = await client.post(
        "/api/v2/feedback",
        json={"nps": 10, "actionable": "yes", "free_text": "great"},
    )
    assert r.status_code == 200
    assert pool.get_conversation(older)["feedback"] is None
    assert pool.get_conversation(newer)["feedback"]["nps"] == 10


@pytest.mark.asyncio
async def test_feedback_503_without_pool(monkeypatch):
    from subprime.core import db as _db

    monkeypatch.setattr(_db, "_pool", None)
    from apps.web.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.get("/api/v2/session")
        r = await c.post(
            "/api/v2/feedback",
            json={"nps": 7, "actionable": "yes", "free_text": None},
        )
        assert r.status_code == 503
