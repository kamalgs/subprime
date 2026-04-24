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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from subprime.core.config import DATABASE_URL
from subprime.core.persistence import InMemorySessionStore, PostgresSessionStore

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
_STATIC_DIR = _HERE / "static"
_SPA_DIST_DIR = _STATIC_DIR / "dist"


def _warm_universe_cache() -> None:
    try:
        from subprime.advisor.planner import warm_universe_cache

        warm_universe_cache()
    except Exception:
        logger.exception("warm_universe_cache skipped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _warm_universe_cache()

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

        try:
            cleared = await app.state.session_store.clear_stale_plan_flags()
            if cleared:
                logger.info("Cleared stale plan_generating flag on %d session(s)", cleared)
        except Exception:
            logger.exception("clear_stale_plan_flags failed")

        try:
            from subprime.flags import init_flags

            await init_flags(pool)
            logger.info("Feature flags initialised")
        except Exception:
            logger.exception("flags init failed — falling back to defaults")
    else:
        app.state.session_store = InMemorySessionStore()
        logger.info("Using in-memory session store (no DATABASE_URL)")

    yield

    if DATABASE_URL:
        from subprime.core.db import close_pool

        await close_pool()


def create_app() -> FastAPI:
    from apps.web.api_v2 import router as api_v2_router

    app = FastAPI(title="Benji", description="Your personal mutual fund advisor", lifespan=lifespan)
    app.state.session_store = InMemorySessionStore()
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    app.include_router(api_v2_router)

    try:
        from subprime.observability import instrument_fastapi

        instrument_fastapi(app)
    except Exception:
        logger.exception("FastAPI OTEL instrumentation failed")

    spa_index = _SPA_DIST_DIR / "index.html"
    if not spa_index.exists():
        raise RuntimeError(
            f"SPA build missing at {spa_index}. Run `make frontend` before starting the app."
        )

    logger.info("Serving React SPA from %s", _SPA_DIST_DIR)
    assets_dir = _SPA_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="spa-assets")

    async def _serve_index(request: Request) -> FileResponse:  # noqa: ARG001
        return FileResponse(spa_index)

    app.get("/", include_in_schema=False)(_serve_index)
    app.get("/step/{path:path}", include_in_schema=False)(_serve_index)
    app.get("/app/{path:path}", include_in_schema=False)(_serve_index)
    app.get("/verify", include_in_schema=False)(_serve_index)

    return app
