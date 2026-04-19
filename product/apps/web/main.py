# apps/web/main.py
"""FastAPI application factory for the Benji advisor wizard."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from subprime.core.config import DATABASE_URL
from subprime.core.persistence import InMemorySessionStore, PostgresSessionStore

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"


def _migrate_duckdb_schema() -> None:
    """Apply any pending DuckDB schema migrations to the fund universe store.

    Idempotent — safe to run on every startup. No-op if the DB file doesn't
    exist yet (a `subprime data refresh` will create it).
    """
    try:
        import duckdb
        from subprime.core.config import DB_PATH
        from subprime.data.store import ensure_schema
        if not DB_PATH.exists():
            logger.info("DuckDB file %s not found — skipping migration", DB_PATH)
            return
        conn = duckdb.connect(str(DB_PATH))  # writable
        try:
            ensure_schema(conn)
            logger.info("DuckDB schema migrations applied to %s", DB_PATH)
        finally:
            conn.close()
    except Exception:
        logger.exception("DuckDB schema migration failed — continuing anyway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB pool if configured. Shutdown: close pool."""
    _migrate_duckdb_schema()

    if DATABASE_URL:
        from subprime.core.db import init_pool

        pool = await init_pool(DATABASE_URL)
        app.state.session_store = PostgresSessionStore(pool)
        logger.info("Using PostgreSQL session store")
    else:
        app.state.session_store = InMemorySessionStore()
        logger.info("Using in-memory session store (no DATABASE_URL)")

    yield

    if DATABASE_URL:
        from subprime.core.db import close_pool

        await close_pool()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from apps.web import api, routes

    app = FastAPI(title="Benji", description="Your personal mutual fund advisor", lifespan=lifespan)

    # Default to in-memory — lifespan upgrades to Postgres if DATABASE_URL is set
    app.state.session_store = InMemorySessionStore()
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    app.include_router(routes.router)
    app.include_router(api.router)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/step/1", status_code=307)

    return app
