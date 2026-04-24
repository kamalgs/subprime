"""Tests for subprime.flags — cache behaviour and GrowthBook evaluation.

Uses a fake asyncpg pool so no real DB is required.
"""

from __future__ import annotations

from typing import Any

import pytest


class _FakeConn:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.executed: list[tuple[str, tuple]] = []

    async def fetch(self, sql: str, *args: Any) -> list[dict]:
        return list(self._rows)

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed.append((sql, args))
        # Very small shim: pretend an INSERT/UPDATE wrote or deleted 1 row
        if "DELETE" in sql:
            before = len(self._rows)
            self._rows = [r for r in self._rows if r["key"] != args[0]]
            return f"DELETE {before - len(self._rows)}"
        # Upsert
        key = args[0]
        row = {"key": key, "definition": args[1], "description": args[2] or "", "updated_at": None}
        for i, r in enumerate(self._rows):
            if r["key"] == key:
                self._rows[i] = row
                return "INSERT 0 1"
        self._rows.append(row)
        return "INSERT 0 1"


class _FakePool:
    def __init__(self, rows: list[dict] | None = None):
        self._conn = _FakeConn(rows or [])

    def acquire(self):
        pool = self

        class _Acq:
            async def __aenter__(self_inner):
                return pool._conn

            async def __aexit__(self_inner, *a):
                return None

        return _Acq()


@pytest.fixture(autouse=True)
def _reset_flags_module():
    """Force module-level state back to cold between tests."""
    from subprime.flags import _store

    _store._pool = None
    _store._cache = {}
    _store._cache_expiry = 0.0
    _store._cache_lock = None
    yield


@pytest.mark.asyncio
async def test_defaults_when_uninitialised() -> None:
    from subprime.flags import get_value, is_on

    # No init_flags called → pool is None, cache empty, evaluator returns default
    assert await is_on("anything") is False
    assert await is_on("anything", default=True) is True
    assert await get_value("missing", default="fallback") == "fallback"


@pytest.mark.asyncio
async def test_simple_on_off_flag_evaluates() -> None:
    from subprime.flags import init_flags, is_on

    pool = _FakePool(rows=[{"key": "plan_extended", "definition": {"defaultValue": True}}])
    await init_flags(pool, ttl_seconds=0.0)
    assert await is_on("plan_extended") is True


@pytest.mark.asyncio
async def test_set_flag_invalidates_cache() -> None:
    from subprime.flags import init_flags, is_on, set_flag

    pool = _FakePool(rows=[{"key": "flag_a", "definition": {"defaultValue": False}}])
    await init_flags(pool, ttl_seconds=60.0)
    assert await is_on("flag_a") is False

    await set_flag("flag_a", definition={"defaultValue": True})
    # Next read must see the update even though TTL hasn't elapsed
    assert await is_on("flag_a") is True


@pytest.mark.asyncio
async def test_get_value_returns_non_bool() -> None:
    from subprime.flags import get_value, init_flags

    pool = _FakePool(rows=[{"key": "model", "definition": {"defaultValue": "flash"}}])
    await init_flags(pool, ttl_seconds=0.0)
    assert await get_value("model") == "flash"
    assert await get_value("missing", default="x") == "x"


@pytest.mark.asyncio
async def test_rollout_by_attribute() -> None:
    """GrowthBook-shaped flag with a force rule based on session_id."""
    from subprime.flags import init_flags, is_on

    definition = {
        "defaultValue": False,
        "rules": [{"condition": {"session_id": "abc"}, "force": True}],
    }
    pool = _FakePool(rows=[{"key": "beta", "definition": definition}])
    await init_flags(pool, ttl_seconds=0.0)

    assert await is_on("beta", ctx={"session_id": "abc"}) is True
    assert await is_on("beta", ctx={"session_id": "other"}) is False
