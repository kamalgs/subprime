"""Initial schema: sessions, conversations, otps.

Revision ID: 001
Create Date: 2026-04-12
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            current_step INTEGER NOT NULL DEFAULT 1,
            mode TEXT NOT NULL DEFAULT 'basic',
            data JSONB NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);

        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            investor_name TEXT,
            mode TEXT NOT NULL,
            profile JSONB,
            strategy JSONB,
            plan JSONB,
            strategy_chat JSONB DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at DESC);

        CREATE TABLE IF NOT EXISTS otps (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            verified_at TIMESTAMPTZ,
            session_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_otps_email ON otps(email, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_otps_code ON otps(code);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS otps;")
    op.execute("DROP TABLE IF EXISTS conversations;")
    op.execute("DROP TABLE IF EXISTS sessions;")
