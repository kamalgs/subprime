"""JSON-only REST API for the React frontend.

All endpoints mounted under /api/v2.
"""

from __future__ import annotations

from fastapi import APIRouter

from apps.web.api_v2 import personas, plan, session, strategy

router = APIRouter(prefix="/api/v2", tags=["v2"])
router.include_router(session.router)
router.include_router(personas.router)
router.include_router(strategy.router)
router.include_router(plan.router)
