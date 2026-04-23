"""DuckDB store for the curated mutual fund universe.

Provides a thin persistence layer around a local DuckDB file:

- :func:`get_connection` opens/creates the database file (parent dirs included).
- :func:`ensure_schema` creates the fund-universe tables if they do not exist.
- :func:`log_refresh` / :func:`get_refresh_stats` track refresh history.

Business logic (ingestion, curation) lives in later modules — this file is
the foundation they build on.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb

from subprime.core.config import DB_PATH


# --------------------------------------------------------------------------- #
# DDL
# --------------------------------------------------------------------------- #

_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schemes (
        amfi_code        VARCHAR PRIMARY KEY,
        name             VARCHAR,
        nav_name         VARCHAR,
        amc              VARCHAR,
        scheme_type      VARCHAR,
        scheme_category  VARCHAR,
        plan_type        VARCHAR,
        nav              DOUBLE,
        latest_nav_date  DATE,
        average_aum_cr   DOUBLE,
        launch_date      DATE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nav_history (
        amfi_code  VARCHAR,
        nav_date   DATE,
        nav        DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fund_returns (
        amfi_code         VARCHAR PRIMARY KEY,
        returns_1y        DOUBLE,
        returns_3y        DOUBLE,
        returns_5y        DOUBLE,
        -- Risk metrics computed from 1-year NAV history vs Nifty 50 benchmark
        volatility_1y     DOUBLE,   -- annualised std dev of daily returns (%)
        beta              DOUBLE,   -- sensitivity to Nifty 50 (1.0 = market)
        alpha             DOUBLE,   -- Jensen's alpha vs benchmark, annualised (%)
        tracking_error    DOUBLE,   -- annualised std dev of daily excess returns (%)
        sharpe_ratio      DOUBLE,   -- (annualised_return - 7%) / volatility
        information_ratio DOUBLE,   -- alpha / tracking_error
        last_computed_at  TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fund_universe (
        amfi_code         VARCHAR PRIMARY KEY,
        name              VARCHAR,
        display_name      VARCHAR,   -- LLM-curated short name for UI (e.g. "HDFC Nifty 50 Index")
        amc               VARCHAR,
        category          VARCHAR,
        sub_category      VARCHAR,
        aum_cr            DOUBLE,
        launch_date       DATE,
        returns_1y        DOUBLE,
        returns_3y        DOUBLE,
        returns_5y        DOUBLE,
        expense_ratio     DOUBLE,
        rank_in_category  INTEGER,
        -- Risk metrics (joined from fund_returns during universe build)
        volatility_1y     DOUBLE,
        beta              DOUBLE,
        alpha             DOUBLE,
        tracking_error    DOUBLE,
        sharpe_ratio      DOUBLE,
        information_ratio DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS refresh_log (
        refreshed_at   TIMESTAMP,
        scheme_count   INTEGER,
        nav_count      INTEGER
    )
    """,
)


# --------------------------------------------------------------------------- #
# Connection / schema
# --------------------------------------------------------------------------- #


def get_connection(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open (or create) the DuckDB file, ensuring the parent directory exists.

    Parameters
    ----------
    db_path:
        Optional override for the database path. Defaults to
        :data:`subprime.core.config.DB_PATH`.
    """
    path = Path(db_path) if db_path is not None else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all fund-universe tables if they do not exist (idempotent).

    Also applies light schema migrations for columns added after the initial
    release (e.g. ``fund_universe.expense_ratio``).
    """
    for statement in _SCHEMA_STATEMENTS:
        conn.execute(statement)

    # Migrations: add columns introduced after initial release.
    universe_cols = {
        row[1] for row in conn.execute("PRAGMA table_info('fund_universe')").fetchall()
    }
    for col in (
        "expense_ratio",
        "volatility_1y",
        "beta",
        "alpha",
        "tracking_error",
        "sharpe_ratio",
        "information_ratio",
    ):
        if col not in universe_cols:
            conn.execute(f"ALTER TABLE fund_universe ADD COLUMN {col} DOUBLE")
    if "launch_date" not in universe_cols:
        conn.execute("ALTER TABLE fund_universe ADD COLUMN launch_date DATE")
    if "display_name" not in universe_cols:
        conn.execute("ALTER TABLE fund_universe ADD COLUMN display_name VARCHAR")

    returns_cols = {row[1] for row in conn.execute("PRAGMA table_info('fund_returns')").fetchall()}
    for col in (
        "volatility_1y",
        "beta",
        "alpha",
        "tracking_error",
        "sharpe_ratio",
        "information_ratio",
    ):
        if col not in returns_cols:
            conn.execute(f"ALTER TABLE fund_returns ADD COLUMN {col} DOUBLE")


# --------------------------------------------------------------------------- #
# Refresh log
# --------------------------------------------------------------------------- #


def log_refresh(
    conn: duckdb.DuckDBPyConnection,
    scheme_count: int,
    nav_count: int,
) -> None:
    """Record a refresh event with the current UTC timestamp."""
    conn.execute(
        "INSERT INTO refresh_log (refreshed_at, scheme_count, nav_count) VALUES (?, ?, ?)",
        [datetime.now(timezone.utc), scheme_count, nav_count],
    )


def get_refresh_stats(conn: duckdb.DuckDBPyConnection) -> dict | None:
    """Return the most recent refresh record, or ``None`` if no refreshes exist."""
    row = conn.execute(
        """
        SELECT refreshed_at, scheme_count, nav_count
        FROM refresh_log
        ORDER BY refreshed_at DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return {
        "refreshed_at": row[0],
        "scheme_count": row[1],
        "nav_count": row[2],
    }
