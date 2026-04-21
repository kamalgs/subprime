"""Conversation logging — saves completed sessions for replay and analysis."""

from __future__ import annotations
import json
import logging
from pathlib import Path
from subprime.core.models import Session

logger = logging.getLogger(__name__)


async def save_conversation(
    session: Session, pool=None, conversations_dir: Path | None = None
) -> Path | None:
    """Save a completed session. Returns JSON file path (fallback) or None (Postgres)."""
    record = _session_to_record(session)

    if pool is not None:
        await pool.execute(
            """INSERT INTO conversations (session_id, investor_name, mode, profile, strategy, plan, strategy_chat)
               VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb)""",
            record["session_id"],
            record["investor_name"],
            record["mode"],
            json.dumps(record["profile"], default=str),
            json.dumps(record["strategy"], default=str),
            json.dumps(record["plan"], default=str),
            json.dumps(record["strategy_chat"], default=str),
        )
        logger.info("Conversation saved to database: session=%s", session.id)
        return None

    # Fallback: JSON file
    if conversations_dir is None:
        from subprime.core.config import CONVERSATIONS_DIR

        conversations_dir = CONVERSATIONS_DIR
    conversations_dir.mkdir(parents=True, exist_ok=True)
    path = conversations_dir / f"{session.id}.json"
    path.write_text(json.dumps(record, indent=2, default=str))
    logger.info("Conversation saved to file: %s", path)
    return path


async def list_conversations(
    pool=None, conversations_dir: Path | None = None, limit: int = 50
) -> list[dict]:
    """List recent conversations."""
    if pool is not None:
        rows = await pool.fetch(
            "SELECT session_id, investor_name, mode, created_at FROM conversations ORDER BY created_at DESC LIMIT $1",
            limit,
        )
        return [dict(r) for r in rows]

    if conversations_dir is None:
        from subprime.core.config import CONVERSATIONS_DIR

        conversations_dir = CONVERSATIONS_DIR
    if not conversations_dir.exists():
        return []
    files = sorted(conversations_dir.glob("*.json"), reverse=True)[:limit]
    return [json.loads(f.read_text()) for f in files]


def _session_to_record(session: Session) -> dict:
    return {
        "session_id": session.id,
        "investor_name": session.profile.name if session.profile else None,
        "mode": session.mode,
        "profile": session.profile.model_dump() if session.profile else None,
        "strategy": session.strategy.model_dump() if session.strategy else None,
        "plan": session.plan.model_dump() if session.plan else None,
        "strategy_chat": [t.model_dump() for t in session.strategy_chat],
    }
