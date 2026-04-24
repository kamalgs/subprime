"""Postgres-backed feature flag store + GrowthBook evaluator.

All flag state lives in the ``feature_flags`` table (see migration 002).
Evaluation goes through GrowthBook's Python SDK so we get targeting
rules, rollout percentages, and A/B experiments without writing our own
bucketing logic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from growthbook import GrowthBook

logger = logging.getLogger(__name__)

# Module-level cache. init_flags() bolts the pool on at startup.
_pool = None  # type: Any
_cache: dict[str, dict] = {}
_cache_expiry: float = 0.0
_cache_ttl_seconds: float = 30.0
_cache_lock: asyncio.Lock | None = None


async def init_flags(pool: Any, *, ttl_seconds: float = 30.0) -> None:
    """Wire the flags module to an asyncpg pool and prime the cache.

    Safe to call at startup even before the feature_flags table has any
    rows — a missing table or empty result just means every flag falls
    back to its default.
    """
    global _pool, _cache_ttl_seconds, _cache_lock
    _pool = pool
    _cache_ttl_seconds = ttl_seconds
    _cache_lock = asyncio.Lock()
    try:
        await _refresh_cache(force=True)
    except Exception:
        logger.exception("flags: initial cache refresh failed — falling back to defaults")


async def _refresh_cache(*, force: bool = False) -> dict[str, dict]:
    """Return the flag map, hitting Postgres only when the TTL is up."""
    global _cache, _cache_expiry

    now = time.monotonic()
    if not force and now < _cache_expiry and _cache:
        return _cache
    if _pool is None:
        return _cache  # no pool wired → use whatever's already there (empty)

    assert _cache_lock is not None
    async with _cache_lock:
        if not force and time.monotonic() < _cache_expiry and _cache:
            return _cache
        try:
            async with _pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT key, definition FROM feature_flags",
                )
        except Exception:
            # Table missing / connection error → keep stale cache.
            logger.exception("flags: Postgres fetch failed")
            return _cache

        new_cache: dict[str, dict] = {}
        for row in rows:
            raw = row["definition"]
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("flags: bad JSON for key=%s — skipping", row["key"])
                    continue
            new_cache[row["key"]] = raw or {"defaultValue": False}
        _cache = new_cache
        _cache_expiry = time.monotonic() + _cache_ttl_seconds
    return _cache


def _evaluate(
    features: dict[str, dict],
    key: str,
    default: Any,
    ctx: dict[str, Any] | None,
) -> Any:
    """Run GrowthBook's evaluator on *features* for a single key."""
    attributes = dict(ctx or {})
    gb = GrowthBook(attributes=attributes, features=features)
    result = gb.eval_feature(key)
    if result is None:
        return default
    value = result.value
    return default if value is None else value


async def is_on(key: str, *, default: bool = False, ctx: dict[str, Any] | None = None) -> bool:
    """Return True when the flag evaluates to a truthy value."""
    features = await _refresh_cache()
    return bool(_evaluate(features, key, default, ctx))


async def get_value(key: str, default: Any = None, *, ctx: dict[str, Any] | None = None) -> Any:
    """Return the flag's evaluated value (any JSON type)."""
    features = await _refresh_cache()
    return _evaluate(features, key, default, ctx)


async def list_flags() -> list[dict]:
    """All flag definitions — for the admin UI."""
    if _pool is None:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, definition, description, updated_at FROM feature_flags ORDER BY key"
        )
    return [
        {
            "key": r["key"],
            "definition": (
                json.loads(r["definition"]) if isinstance(r["definition"], str) else r["definition"]
            ),
            "description": r["description"] or "",
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


async def set_flag(key: str, *, definition: dict, description: str = "") -> None:
    """Upsert a flag definition and invalidate the cache."""
    if _pool is None:
        raise RuntimeError("flags: init_flags(pool) not called")
    payload = json.dumps(definition)
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO feature_flags (key, definition, description, updated_at)
            VALUES ($1, $2::jsonb, $3, NOW())
            ON CONFLICT (key) DO UPDATE SET
              definition = EXCLUDED.definition,
              description = EXCLUDED.description,
              updated_at = NOW()
            """,
            key,
            payload,
            description,
        )
    await _refresh_cache(force=True)


async def delete_flag(key: str) -> bool:
    """Remove a flag. Returns True if a row was deleted."""
    if _pool is None:
        raise RuntimeError("flags: init_flags(pool) not called")
    async with _pool.acquire() as conn:
        result = await conn.execute("DELETE FROM feature_flags WHERE key = $1", key)
    await _refresh_cache(force=True)
    return result.endswith(" 1")
