"""FastAPI app factory for the wizard web app."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from apps.web.session import InMemorySessionStore

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from apps.web import routes, api  # noqa: PLC0415 — deferred to avoid circulars

    app = FastAPI(title="FinAdvisor", description="AI-powered mutual fund advisory")

    # State
    app.state.session_store = InMemorySessionStore()
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    # Static files
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Routers
    app.include_router(routes.router)
    app.include_router(api.router)

    # Root redirect
    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/step/1", status_code=307)

    return app
