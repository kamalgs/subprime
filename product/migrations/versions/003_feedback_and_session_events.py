"""Feedback column on conversations + session_events table.

Revision ID: 003
Create Date: 2026-05-09

Both surfaces were originally stood up by inline ``CREATE TABLE / ALTER
TABLE IF NOT EXISTS`` statements in ``subprime.feedback._store`` (PR
#44). They live on prod already — this migration backfills the schema
history so a fresh DB ends up at the same shape.

``IF NOT EXISTS`` everywhere so it's safe to run against the existing
prod DB once the auto-migrate hook is enabled.
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS feedback JSONB")
    op.execute("""
        CREATE TABLE IF NOT EXISTS session_events (
            id          BIGSERIAL PRIMARY KEY,
            session_id  TEXT NOT NULL,
            kind        TEXT NOT NULL,
            payload     JSONB,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_events_session_kind "
        "ON session_events(session_id, kind)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_session_events_session_kind")
    op.execute("DROP TABLE IF EXISTS session_events")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS feedback")
