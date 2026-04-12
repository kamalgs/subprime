"""asyncpg connection pool management."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)
_pool = None


async def init_pool(database_url: str):
    """Create the global asyncpg connection pool."""
    global _pool
    import asyncpg
    _pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
    logger.info("Database pool created: %s", database_url.split("@")[-1])
    return _pool


def get_pool():
    """Get the current pool, or None if not initialized."""
    return _pool


async def close_pool():
    """Close the global pool if it exists."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")
