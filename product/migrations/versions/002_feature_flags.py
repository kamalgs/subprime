"""Feature flags table.

Revision ID: 002
Create Date: 2026-04-24
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
