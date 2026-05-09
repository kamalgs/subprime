"""Alembic migration smoke tests.

We can't easily spin up a real Postgres in unit tests, so the assertions
here focus on what we *can* verify deterministically without a server:

* the migration scripts parse and form a linear chain (revision graph)
* each migration's SQL contains the expected DDL fragments
* the runner module locates ``alembic.ini`` and the auto-migrate flag
  honours common truthy / falsy values
* env.py is structured to strip the ``+asyncpg`` driver suffix

The end-to-end "upgrade head produces prod schema" assertion is covered
by the manual step documented in ``docs/operations.md`` — it requires a
live Postgres and gets validated as part of the deploy review, not in CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def alembic_config():
    from alembic.config import Config

    ini = Path(__file__).resolve().parent.parent / "migrations" / "alembic.ini"
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(ini.parent))
    return cfg


def test_revision_chain_is_linear(alembic_config):
    """All revisions form a single chain ending at one head (currently 003)."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config)
    heads = script.get_heads()
    assert len(heads) == 1, f"expected exactly one head, got {heads}"

    rev_ids = {r.revision for r in script.walk_revisions()}
    assert {"001", "002", "003"}.issubset(rev_ids)
    assert heads[0] == "003"


def test_baseline_001_creates_core_tables(alembic_config):
    """Baseline migration mentions sessions, conversations, otps."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config)
    rev = script.get_revision("001")
    src = Path(rev.path).read_text()
    for table in ("sessions", "conversations", "otps"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in src, f"baseline missing {table}"


def test_migration_002_creates_feature_flags(alembic_config):
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config)
    rev = script.get_revision("002")
    src = Path(rev.path).read_text()
    assert "CREATE TABLE IF NOT EXISTS feature_flags" in src


def test_migration_003_adds_feedback_and_events(alembic_config):
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config)
    rev = script.get_revision("003")
    src = Path(rev.path).read_text()
    assert "ADD COLUMN IF NOT EXISTS feedback" in src
    assert "session_events" in src
    assert "idx_session_events_session_kind" in src


def test_runner_locates_alembic_ini():
    from subprime.core.migrations import _alembic_ini_path

    p = _alembic_ini_path()
    assert p.exists()
    assert p.name == "alembic.ini"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", True),
        ("true", True),
        ("True", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("", False),
        ("nope", False),
    ],
)
def test_auto_migrate_flag(monkeypatch, value, expected):
    from subprime.core.migrations import auto_migrate_enabled

    monkeypatch.setenv("SUBPRIME_AUTO_MIGRATE", value)
    assert auto_migrate_enabled() is expected


def test_auto_migrate_unset(monkeypatch):
    from subprime.core.migrations import auto_migrate_enabled

    monkeypatch.delenv("SUBPRIME_AUTO_MIGRATE", raising=False)
    assert auto_migrate_enabled() is False


def test_env_py_strips_asyncpg_suffix():
    """env.py contains the asyncpg-suffix-stripping line.

    The actual stripping logic is too intertwined with alembic.context to
    import cleanly, so we assert on the source text — if someone deletes
    the rewrite the test catches it.
    """
    env_path = Path(__file__).resolve().parent.parent / "migrations" / "env.py"
    src = env_path.read_text()
    assert 'replace("postgresql+asyncpg://", "postgresql://"' in src


def test_init_flags_no_longer_creates_table():
    """After Alembic took over, the inline CREATE TABLE was removed."""
    p = Path(__file__).resolve().parent.parent / "src" / "subprime" / "flags" / "_store.py"
    src = p.read_text()
    assert "CREATE TABLE IF NOT EXISTS feature_flags" not in src


def test_init_feedback_no_longer_creates_table():
    p = Path(__file__).resolve().parent.parent / "src" / "subprime" / "feedback" / "_store.py"
    src = p.read_text()
    assert "CREATE TABLE IF NOT EXISTS session_events" not in src
    assert "ADD COLUMN IF NOT EXISTS feedback" not in src
