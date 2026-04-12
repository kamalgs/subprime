# Persistence Layer, OTP Premium Gate, and Conversation Logging

## Goal

Add PostgreSQL persistence to FinAdvisor: session storage, conversation logging, and an email OTP gate for the premium tier (100 OTPs/day to control LLM cost). Shared infrastructure in `core/` so both the web app and CLI can use it.

## Architecture

**PostgreSQL** (Nomad container, `postgres:16-alpine`) stores sessions, conversations, and OTPs. Managed by Alembic migrations. Connected via `asyncpg` pool.

**Module split**: DB, sessions, conversations, and OTP logic live in `src/subprime/core/` (shared). Email sending lives in `apps/web/` (web-only). CLI uses the same persistence layer directly.

## Database

### Connection

- `asyncpg` connection pool, managed in `src/subprime/core/db.py`
- Config: `DATABASE_URL` env var (e.g., `postgresql://finadvisor:password@localhost:5432/finadvisor`)
- Pool created lazily on first use, closed on app shutdown
- Added to `src/subprime/core/config.py` as `DATABASE_URL`

### Tables (Alembic migration `001_initial`)

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    current_step INTEGER NOT NULL DEFAULT 1,
    mode TEXT NOT NULL DEFAULT 'basic',
    data JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_sessions_updated ON sessions(updated_at DESC);

CREATE TABLE conversations (
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
CREATE INDEX idx_conversations_created ON conversations(created_at DESC);

CREATE TABLE otps (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    code TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ,
    session_id TEXT
);
CREATE INDEX idx_otps_email ON otps(email, created_at DESC);
CREATE INDEX idx_otps_code ON otps(code);
CREATE INDEX idx_otps_daily ON otps(created_at) WHERE verified_at IS NULL;
```

### Session storage in JSONB

The `sessions.data` column stores the full session state: `profile`, `strategy`, `plan`, `strategy_chat` — all as JSON-serialized Pydantic models. No ORM mapping of nested models. On read, deserialize back to Pydantic models. This avoids a complex relational schema for deeply nested LLM-generated data.

## File Structure

### Core (shared)

```
src/subprime/core/
├── db.py              # asyncpg pool: init_pool(), get_pool(), close_pool()
├── persistence.py     # SessionStore protocol, PostgresSessionStore, InMemorySessionStore
├── conversations.py   # save_conversation(), list_conversations()
├── otp.py             # create_otp(), verify_otp(), daily_otp_count()
├── config.py          # + DATABASE_URL, SMTP_*, OTP_DAILY_LIMIT, OTP_EXPIRY_MINUTES
└── models.py          # + Session, SessionSummary (moved from apps/web/session.py)
```

### Web (web-specific)

```
apps/web/
├── email.py           # send_otp_email() via SMTP
├── api.py             # + POST /api/request-otp, POST /api/verify-otp
├── session.py         # Thin wrapper, re-exports from core.persistence
├── main.py            # + init DB pool on startup, close on shutdown
└── templates/
    └── step_plan.html # Updated Premium card with OTP flow
```

### Migrations

```
migrations/
├── alembic.ini
├── env.py
└── versions/
    └── 001_initial.py
```

### Nomad

```
nomad/jobs/
└── postgresql.tf      # New PostgreSQL container job
```

## OTP Flow

### Step 1 Premium Card UX

The Premium card gets an inline form below the CTA:

1. **Initial state**: "Start Premium Plan" button. Below it: email input + "Send me a code" button. Small text: "We'll email you a one-time code. 100 premium plans available per day."
2. **After sending**: email input hides, OTP input (6 digits) appears + "Verify" button. Small text: "Code sent to your@email.com. Valid for 10 minutes."
3. **After verification**: session mode set to premium, redirect to Step 2.
4. **Daily limit reached**: "Premium slots are full for today — try again tomorrow." Email form disabled.

### OTP Logic (`core/otp.py`)

```python
async def create_otp(pool, email: str) -> OTPResult:
    """Generate a 6-digit OTP for the given email.
    
    - Checks daily limit (100)
    - Invalidates any existing unexpired OTP for this email
    - Generates new 6-digit code
    - Stores in DB with 10-minute expiry
    - Returns OTPResult(success=True, code="123456") or OTPResult(success=False, reason="...")
    """

async def verify_otp(pool, email: str, code: str) -> bool:
    """Verify an OTP code.
    
    - Checks code exists, matches email, not expired, not already verified
    - Sets verified_at and session_id
    - Returns True/False
    """

async def daily_otp_count(pool) -> int:
    """Count OTPs created today (UTC)."""
```

OTP code: `f"{secrets.randbelow(1_000_000):06d}"` — 6 digits, zero-padded.

### Email (`apps/web/email.py`)

```python
async def send_otp_email(email: str, code: str) -> bool:
    """Send OTP via SMTP. Returns True on success."""
```

Plain text email:
```
Subject: Your FinAdvisor Premium Code

Your one-time code: 123456

Enter this code at https://finadvisor.gkamal.online to start your premium plan.
This code expires in 10 minutes.

— FinAdvisor
```

Config: `SMTP_HOST`, `SMTP_PORT` (default 587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.

### API Endpoints

```
POST /api/request-otp
  Form: email (str)
  → Validates email format
  → Checks daily limit
  → Creates OTP, sends email
  → Returns partial HTML: OTP input form or error message

POST /api/verify-otp  
  Form: email (str), code (str)
  → Verifies OTP
  → On success: sets session mode=premium, returns HX-Redirect to /step/2
  → On failure: returns partial HTML with error "Invalid or expired code"
```

## Session Persistence

### PostgresSessionStore

Implements the existing `SessionStore` protocol:

```python
class PostgresSessionStore:
    def __init__(self, pool: asyncpg.Pool): ...
    
    async def get(self, session_id: str) -> Session | None:
        """SELECT from sessions, deserialize JSONB data into Session model."""
    
    async def save(self, session: Session) -> None:
        """UPSERT into sessions. Serialize profile/strategy/plan/chat to JSONB."""
    
    async def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        """SELECT id, mode, current_step, created_at, updated_at + investor name from data."""
```

### Session and SessionSummary Models

Move from `apps/web/session.py` to `src/subprime/core/models.py`. The web session module becomes a re-export:

```python
# apps/web/session.py
from subprime.core.persistence import InMemorySessionStore, PostgresSessionStore
from subprime.core.models import Session, SessionSummary
```

### App Startup

In `apps/web/main.py`:

```python
@app.on_event("startup")
async def startup():
    if DATABASE_URL:
        pool = await init_pool(DATABASE_URL)
        app.state.session_store = PostgresSessionStore(pool)
    else:
        app.state.session_store = InMemorySessionStore()

@app.on_event("shutdown")  
async def shutdown():
    await close_pool()
```

Falls back to InMemorySessionStore when no DATABASE_URL is set (local dev, tests).

## Conversation Logging

### `core/conversations.py`

```python
async def save_conversation(pool, session: Session) -> None:
    """Insert a conversation row from a completed session."""

async def list_conversations(pool, limit: int = 50) -> list[dict]:
    """List recent conversations (for future admin/replay features)."""
```

Called from:
- `apps/web/api.py` — after plan generation in `/api/generate-plan`
- `src/subprime/cli.py` — after plan generation in `advise` command (replaces JSON file write)

### Fallback

When no `DATABASE_URL` is set, conversation logging falls back to the existing JSON file approach in `CONVERSATIONS_DIR`. The `save_conversation()` function handles both paths.

## PostgreSQL Nomad Job

```hcl
job "postgresql" {
  type = "service"
  group "postgresql" {
    count = 1
    network { mode = "host" }
    volume "postgres_data" {
      type = "host"
      source = "postgres_data"
    }
    task "postgresql" {
      driver = "docker"
      config {
        image = "postgres:16-alpine"
        network_mode = "host"
        ports = ["db"]
      }
      env {
        POSTGRES_DB       = "finadvisor"
        POSTGRES_USER     = "finadvisor"
        POSTGRES_PASSWORD = var.postgres_password
      }
      volume_mount {
        volume      = "postgres_data"
        destination = "/var/lib/postgresql/data"
      }
      resources {
        cpu    = 200
        memory = 256
      }
    }
  }
}
```

Port: 5432 on localhost. Host volume at `/opt/nomad/volumes/postgres_data`.

## Config (env vars)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | None (falls back to in-memory) | PostgreSQL connection string |
| `SMTP_HOST` | None | SMTP server host |
| `SMTP_PORT` | 587 | SMTP port |
| `SMTP_USER` | None | SMTP username |
| `SMTP_PASSWORD` | None | SMTP password |
| `SMTP_FROM` | noreply@finadvisor.gkamal.online | From address |
| `OTP_DAILY_LIMIT` | 100 | Max OTPs generated per day |
| `OTP_EXPIRY_MINUTES` | 10 | OTP validity window |

## What Changes in Existing Code

- `apps/web/session.py` — gutted to re-exports from core
- `apps/web/main.py` — add startup/shutdown hooks for DB pool
- `apps/web/api.py` — add OTP endpoints, add conversation save after plan generation
- `apps/web/templates/step_plan.html` — Premium card OTP flow
- `src/subprime/core/models.py` — add Session, SessionSummary models
- `src/subprime/core/config.py` — add DATABASE_URL, SMTP_*, OTP_* settings
- `src/subprime/cli.py` — use core.conversations instead of JSON file save
- `pyproject.toml` — add asyncpg, alembic dependencies
- `Dockerfile` — no change (asyncpg installed via pip)
- `nomad/jobs/finadvisor.tf` — add DATABASE_URL env var

## Testing

**Unit tests** (mock asyncpg pool):
- `PostgresSessionStore` CRUD operations
- OTP creation, verification, expiry, daily limit
- Conversation save/list
- Email formatting (mock SMTP)

**Integration tests** (real PostgreSQL via testcontainers or similar):
- Full session lifecycle: create → save → get → list
- OTP flow: request → verify → reject expired
- Conversation logging round-trip

**E2E Playwright tests**:
- Premium card: enter email → get OTP → enter code → proceed to Step 2
- Daily limit: show "full for today" message
- Basic flow still works without OTP

**Existing tests**: InMemorySessionStore tests unchanged. All httpx tests continue to use InMemorySessionStore (no DATABASE_URL set).

## Not In Scope

- Admin UI for viewing conversations/OTPs
- User accounts / authentication
- Multiple OTP channels (SMS, WhatsApp)
- Coupon codes (replaced by OTP)
- Rate limiting per email beyond "one active OTP at a time"
