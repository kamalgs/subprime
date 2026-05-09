"""Tests for POST /api/v2/events + admin events GET.

Uses the in-process FakePool to stand in for asyncpg — no real DB
needed. Mirrors the harness pattern in ``test_api_v2.py``.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests._fake_pg import FakePool

ADMIN_TOKEN = "test-admin-token"


@pytest.fixture
async def client_with_pool(monkeypatch):
    """ASGI client + a FakePool wired into subprime.core.db.get_pool().

    Yields ``(client, pool)`` so tests can assert on raw DB state.
    """
    monkeypatch.setenv("SUBPRIME_ADMIN_TOKEN", ADMIN_TOKEN)

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
async def test_events_happy_path(client_with_pool):
    client, pool = client_with_pool
    sid = await _new_session(client)

    body = {
        "events": [
            {"kind": "wizard.tier_picked", "payload": {"mode": "basic"}},
            {"kind": "wizard.profile_submitted", "payload": None},
            {"kind": "plan.viewed", "payload": {"section": "core"}},
        ]
    }
    r = await client.post("/api/v2/events", json=body)
    assert r.status_code == 200, r.text
    assert r.json() == {"accepted": 3}

    rows = pool.all_events(sid)
    assert [r["kind"] for r in rows] == [
        "wizard.tier_picked",
        "wizard.profile_submitted",
        "plan.viewed",
    ]
    assert rows[0]["payload"] == {"mode": "basic"}
    assert rows[1]["payload"] is None


@pytest.mark.asyncio
async def test_events_admin_get_returns_staged_events(client_with_pool):
    client, _pool = client_with_pool
    sid = await _new_session(client)

    body = {"events": [{"kind": "click.cta", "payload": {"label": "start"}}]}
    await client.post("/api/v2/events", json=body)

    r = await client.get(
        f"/api/v2/admin/sessions/{sid}/events",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == sid
    assert len(data["events"]) == 1
    assert data["events"][0]["kind"] == "click.cta"
    assert data["events"][0]["payload"] == {"label": "start"}


@pytest.mark.asyncio
async def test_events_admin_get_requires_token(client_with_pool):
    client, _pool = client_with_pool
    sid = await _new_session(client)
    r = await client.get(f"/api/v2/admin/sessions/{sid}/events")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_events_rejects_too_many(client_with_pool):
    client, pool = client_with_pool
    await _new_session(client)
    body = {"events": [{"kind": "x", "payload": None} for _ in range(51)]}
    r = await client.post("/api/v2/events", json=body)
    assert r.status_code == 422
    # No partial inserts
    assert pool.all_events() == []


@pytest.mark.asyncio
async def test_events_rejects_empty_batch(client_with_pool):
    client, _pool = client_with_pool
    await _new_session(client)
    r = await client.post("/api/v2/events", json={"events": []})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_events_rejects_missing_kind(client_with_pool):
    client, pool = client_with_pool
    await _new_session(client)
    # Missing 'kind'
    r = await client.post(
        "/api/v2/events",
        json={"events": [{"payload": {"foo": 1}}]},
    )
    assert r.status_code == 422
    assert pool.all_events() == []


@pytest.mark.asyncio
async def test_events_bulk_insert_atomic(client_with_pool, monkeypatch):
    """If executemany fails mid-batch, no rows should be visible."""
    client, pool = client_with_pool
    await _new_session(client)

    # Patch insert_events to raise after partial work — simulate a
    # failure inside the transaction. The route should bubble up 500
    # and the transaction context manager keeps the DB clean.
    from subprime.feedback import _store as feedback_store

    original = feedback_store.insert_events

    async def _boom(pool_, session_id, events):
        # Start a transaction, write one row, then raise — the FakePool
        # rolls the snapshot back on exit.
        async with pool_.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO session_events (session_id, kind, payload) VALUES ($1, $2, $3::jsonb)",
                    session_id,
                    "first",
                    None,
                )
                raise RuntimeError("simulated mid-batch failure")

    monkeypatch.setattr(feedback_store, "insert_events", _boom)
    # The route imports insert_events from the package re-export, so
    # patch there too:
    from apps.web.api_v2 import events as events_route

    monkeypatch.setattr(events_route, "insert_events", _boom)

    r = await client.post(
        "/api/v2/events",
        json={"events": [{"kind": "a"}, {"kind": "b"}]},
    )
    assert r.status_code == 500
    assert pool.all_events() == []  # rollback worked

    # Restore for follow-on tests in the same module
    monkeypatch.setattr(feedback_store, "insert_events", original)


@pytest.mark.asyncio
async def test_events_503_when_no_pool(monkeypatch):
    """Without a Postgres pool the endpoint should refuse, not silently drop."""
    monkeypatch.setenv("SUBPRIME_ADMIN_TOKEN", ADMIN_TOKEN)
    from subprime.core import db as _db

    monkeypatch.setattr(_db, "_pool", None)

    from apps.web.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        await c.get("/api/v2/session")
        r = await c.post("/api/v2/events", json={"events": [{"kind": "x"}]})
        assert r.status_code == 503
