"""Feature flags table.

Revision ID: 002
Create Date: 2026-04-24

Note: prod was already running this table (created at startup by
``subprime.flags.init_flags``) before Alembic was wired into the deploy.
The ``CREATE TABLE IF NOT EXISTS`` keeps this migration safe to run
against a DB where the table is pre-existing — required because prod is
stamped at 001 and will pick this up on first auto-migrate.
"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS feature_flags (
            key          TEXT PRIMARY KEY,
            definition   JSONB NOT NULL,
            description  TEXT NOT NULL DEFAULT '',
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS feature_flags;")
