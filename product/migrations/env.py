"""Alembic migration environment.

Reads ``DATABASE_URL`` from the environment (same var the runtime app
uses). The runtime stack is asyncpg, so we drive Alembic with
SQLAlchemy's async engine over asyncpg too — that way one DSN works
for both layers and we don't need to add a sync Postgres driver
(psycopg2 / psycopg3) to the runtime image.

Pure SQL migrations (no ORM models), so ``target_metadata`` stays None.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from alembic import context

# Make ``subprime`` importable when running ``alembic`` from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

config = context.config


def _resolve_database_url(*, async_driver: bool = True) -> str:
    """Pick the DSN; force the ``+asyncpg`` SQLAlchemy driver suffix.

    ``async_driver=True`` returns a DSN suitable for ``create_async_engine``
    (``postgresql+asyncpg://...``). ``False`` returns the bare DSN — used
    only by offline mode where Alembic doesn't actually connect.
    """
    url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set and alembic.ini has no sqlalchemy.url; Alembic cannot connect."
        )
    # Normalise: accept either ``postgres://``, ``postgresql://``, or
    # ``postgresql+asyncpg://`` from the runtime / docs.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    bare = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if not async_driver:
        return bare
    return bare.replace("postgresql://", "postgresql+asyncpg://", 1)


target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_database_url(async_driver=False),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_migrations_online_async() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_resolve_database_url(async_driver=True))
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_migrations_online_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
