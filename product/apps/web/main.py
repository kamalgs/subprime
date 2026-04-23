# apps/web/main.py
"""FastAPI application factory for the Benji advisor wizard."""

from __future__ import annotations

import faulthandler
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Default to INFO so background-task lifecycle logs (plan QUEUED / START /
# DONE / FAILED) land in container stderr. Set LOG_LEVEL=DEBUG for verbose.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)

# On SIGUSR1, dump the stacks of every Python thread to stderr. Lets us
# diagnose a stuck worker with `kill -USR1 <pid>` without attaching a debugger.
try:
    faulthandler.register(signal.SIGUSR1, file=sys.stderr, all_threads=True)
except (AttributeError, ValueError):
    pass  # SIGUSR1 not available (Windows) — silently skip

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from subprime.core.config import DATABASE_URL
from subprime.core.persistence import InMemorySessionStore, PostgresSessionStore

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"
_SPA_DIST_DIR = _STATIC_DIR / "dist"  # Vite build output


def _warm_universe_cache() -> None:
    """Render the fund-universe markdown to disk once so per-request
    plan generation doesn't pay the DuckDB + markdown cost on the hot path."""
    try:
        from subprime.advisor.planner import warm_universe_cache

        warm_universe_cache()
    except Exception:
        logger.exception("warm_universe_cache skipped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: warm universe cache, init DB pool. Shutdown: close pool.

    Schema migrations are **not** done here anymore — run ``subprime data
    migrate`` out-of-band (e.g. as a Nomad prestart task) so the web app
    only holds read-only DuckDB connections at runtime. This avoids lock
    contention when running multiple uvicorn workers.
    """
    _warm_universe_cache()

    # Initialise OpenTelemetry. No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
    try:
        from subprime.observability import setup as otel_setup

        otel_setup()
    except Exception:
        logger.exception("OTEL setup failed (continuing without telemetry)")

    if DATABASE_URL:
        from subprime.core.db import init_pool

        pool = await init_pool(DATABASE_URL)
        app.state.session_store = PostgresSessionStore(pool)
        logger.info("Using PostgreSQL session store")

        # Any plan-generation background tasks from a prior process are dead;
        # reset the flag so users aren't stuck on the loading page.
        try:
            cleared = await app.state.session_store.clear_stale_plan_flags()
            if cleared:
                logger.info("Cleared stale plan_generating flag on %d session(s)", cleared)
        except Exception:
            logger.exception("clear_stale_plan_flags failed")
    else:
        app.state.session_store = InMemorySessionStore()
        logger.info("Using in-memory session store (no DATABASE_URL)")

    yield

    if DATABASE_URL:
        from subprime.core.db import close_pool

        await close_pool()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from apps.web import api
    from apps.web.api_v2 import router as api_v2_router
    from fastapi.responses import FileResponse

    app = FastAPI(title="Benji", description="Your personal mutual fund advisor", lifespan=lifespan)

    # Default to in-memory — lifespan upgrades to Postgres if DATABASE_URL is set
    app.state.session_store = InMemorySessionStore()
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # APIs always first (highest specificity)
    app.include_router(api.router)
    app.include_router(api_v2_router)

    # Wrap with the OTEL ASGI middleware. Safe even when OTEL is unset
    # (no-op tracer/meter providers).
    try:
        from subprime.observability import instrument_fastapi

        instrument_fastapi(app)
    except Exception:
        logger.exception("FastAPI OTEL instrumentation failed")

    spa_index = _SPA_DIST_DIR / "index.html"
    if spa_index.exists():
        # SPA mode: serve React for / and /step/* — the legacy Jinja wizard
        # is NOT mounted. /api/* routes above still win because they're more
        # specific than the catch-all below.
        logger.info("Serving React SPA from %s", _SPA_DIST_DIR)

        # Vite build outputs assets with absolute /assets/* paths in index.html
        assets_dir = _SPA_DIST_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="spa-assets")

        async def _serve_index(request: Request) -> FileResponse:  # noqa: ARG001
            return FileResponse(spa_index)

        app.get("/", include_in_schema=False)(_serve_index)
        app.get("/step/{path:path}", include_in_schema=False)(_serve_index)
        app.get("/app/{path:path}", include_in_schema=False)(_serve_index)
    else:
        # No SPA build — fall back to the legacy Jinja wizard routes.
        logger.info("No SPA build at %s — serving legacy Jinja templates", _SPA_DIST_DIR)
        from apps.web import routes

        app.include_router(routes.router)

        @app.get("/", include_in_schema=False)
        async def root() -> RedirectResponse:
            return RedirectResponse(url="/step/1", status_code=307)

    return app
