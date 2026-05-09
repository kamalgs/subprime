"""Feedback + session-event capture.

Two pieces of plumbing:

* ``conversations.feedback`` (JSONB) — NPS-style post-plan feedback,
  written once per conversation. Idempotent: replaces whatever is there.
* ``session_events`` table — append-only log of UX telemetry events
  bulk-staged from the SPA (e.g. wizard step transitions, button clicks).

Both surfaces are wired into the existing CREATE-IF-NOT-EXISTS startup
path, no Alembic involved (mirrors ``subprime.flags.init_flags``).
"""

from subprime.feedback._store import (
    fetch_session_events,
    init_feedback,
    insert_events,
    upsert_feedback,
)

__all__ = [
    "fetch_session_events",
    "init_feedback",
    "insert_events",
    "upsert_feedback",
]
