# apps/web/main.py
"""FastAPI application factory for the FinAdvisor wizard."""

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB pool if configured. Shutdown: close pool."""
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

    app = FastAPI(title="FinAdvisor", description="AI-powered mutual fund advisory", lifespan=lifespan)

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
