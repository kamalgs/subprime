"""Run Alembic migrations programmatically at app startup.

The deploy wires this in via the FastAPI lifespan (see
``apps/web/main.py``). Gated by the ``SUBPRIME_AUTO_MIGRATE`` env var so
the first deploy with this code can ship without running migrations
until prod has been stamped at the right baseline (see
``docs/operations.md`` → Database / migrations).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _alembic_ini_path() -> Path:
    """Locate ``alembic.ini`` regardless of where the process was launched.

    The product layout is ``product/migrations/alembic.ini``; in the
    container we copy ``product/`` to ``/app`` so the ini ends up at
    ``/app/migrations/alembic.ini``. ``subprime`` lives at
    ``<root>/src/subprime`` (or ``/app/src/subprime`` in the image).
    """
    here = Path(__file__).resolve()
    # walk up: subprime/core/migrations.py → subprime/core → subprime → src → <root>
    candidates = [
        here.parents[3] / "migrations" / "alembic.ini",  # /app/migrations/alembic.ini
        here.parents[3] / "product" / "migrations" / "alembic.ini",  # local repo
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"alembic.ini not found. Looked at: {[str(p) for p in candidates]}")


def auto_migrate_enabled() -> bool:
    """True when ``SUBPRIME_AUTO_MIGRATE`` is set to a truthy value."""
    return os.environ.get("SUBPRIME_AUTO_MIGRATE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _run_upgrade(database_url: str) -> None:
    """Run ``alembic upgrade head`` in the current (sync) thread.

    Internal — call ``run_migrations`` from app code. Split out so the
    async wrapper can dispatch this onto a worker thread without
    duplicating the config wiring.
    """
    from alembic import command
    from alembic.config import Config

    ini_path = _alembic_ini_path()
    cfg = Config(str(ini_path))
    # Alembic resolves ``script_location`` relative to its CWD by default,
    # so pin it to the absolute path next to the ini file.
    cfg.set_main_option("script_location", str(ini_path.parent))
    # ``env.py`` reads ``DATABASE_URL`` from os.environ — make sure it's
    # set even if the caller built the DSN from elsewhere.
    os.environ["DATABASE_URL"] = database_url

    logger.info("Running Alembic upgrade head (config=%s)", ini_path)
    command.upgrade(cfg, "head")
    logger.info("Alembic upgrade complete")


def run_migrations(database_url: str) -> None:
    """Apply all pending migrations against *database_url* (sync API).

    Use this from CLI / scripts. From inside the FastAPI lifespan call
    ``arun_migrations`` instead — env.py spins up its own asyncio loop
    via SQLAlchemy's async engine, which collides with an already-running
    loop.

    Raises on any failure; the caller should let that propagate so a
    half-migrated DB doesn't get traffic.
    """
    _run_upgrade(database_url)


async def arun_migrations(database_url: str) -> None:
    """Async wrapper that runs the upgrade on a worker thread.

    The FastAPI lifespan is already inside an asyncio loop; env.py's
    online mode opens its own loop via ``asyncio.run``, which would
    fail in that context. Off-loading to a thread sidesteps the
    nested-loop problem and keeps the lifespan non-blocking.
    """
    import asyncio

    await asyncio.to_thread(_run_upgrade, database_url)
