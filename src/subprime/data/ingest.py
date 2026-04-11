"""Ingest pipeline for the curated mutual fund dataset.

Downloads the scheme details CSV and NAV history parquet from the upstream
GitHub repository, loads them into the local DuckDB store, and computes
1y/3y/5y CAGR per scheme.

Public API
----------
- :func:`load_schemes`       — load scheme details CSV into ``schemes``.
- :func:`load_nav_history`   — load NAV history parquet into ``nav_history``.
- :func:`compute_returns`    — compute CAGR per scheme into ``fund_returns``.
- :func:`download_dataset`   — async: download both files from GitHub.
- :func:`refresh`            — async orchestrator over the whole pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import duckdb
import httpx

from subprime.core.config import NAV_PARQUET_URL, SCHEMES_CSV_URL
from subprime.data.store import log_refresh

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #


def load_schemes(conn: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """Load the scheme details CSV into the ``schemes`` table.

    Replaces existing rows. Returns the final row count.
    """
    conn.execute("DELETE FROM schemes")
    conn.execute(
        """
        INSERT INTO schemes (
            amfi_code,
            name,
            amc,
            scheme_type,
            scheme_category,
            nav,
            latest_nav_date,
            average_aum_cr,
            launch_date
        )
        SELECT
            CAST(Scheme_Code AS VARCHAR)       AS amfi_code,
            Scheme_Name                        AS name,
            AMC                                AS amc,
            Scheme_Type                        AS scheme_type,
            Scheme_Category                    AS scheme_category,
            TRY_CAST(NAV AS DOUBLE)            AS nav,
            TRY_CAST(Latest_NAV_Date AS DATE)  AS latest_nav_date,
            TRY_CAST(Average_AUM_Cr AS DOUBLE) AS average_aum_cr,
            TRY_CAST(Launch_Date AS DATE)      AS launch_date
        FROM read_csv_auto(?, header=True)
        """,
        [str(csv_path)],
    )
    return conn.execute("SELECT COUNT(*) FROM schemes").fetchone()[0]


def load_nav_history(conn: duckdb.DuckDBPyConnection, parquet_path: Path) -> int:
    """Load the NAV history parquet into the ``nav_history`` table.

    Replaces existing rows. Returns the final row count.
    """
    conn.execute("DELETE FROM nav_history")
    conn.execute(
        """
        INSERT INTO nav_history (amfi_code, nav_date, nav)
        SELECT
            CAST(Scheme_Code AS VARCHAR) AS amfi_code,
            CAST(Date AS DATE)           AS nav_date,
            CAST(NAV AS DOUBLE)          AS nav
        FROM read_parquet(?)
        """,
        [str(parquet_path)],
    )
    return conn.execute("SELECT COUNT(*) FROM nav_history").fetchone()[0]


# --------------------------------------------------------------------------- #
# Returns
# --------------------------------------------------------------------------- #


def compute_returns(conn: duckdb.DuckDBPyConnection) -> int:
    """Compute 1y/3y/5y CAGR for every scheme with sufficient history.

    For each scheme we take the latest NAV and locate the NAV closest to
    (last_date - Ny), within a tolerance window (±30d / ±60d / ±90d). NULLs
    are used wherever the window has no matching observation.

    Replaces existing rows. Returns the final row count.
    """
    conn.execute("DELETE FROM fund_returns")
    conn.execute(
        """
        INSERT INTO fund_returns (
            amfi_code,
            returns_1y,
            returns_3y,
            returns_5y,
            last_computed_at
        )
        WITH latest AS (
            SELECT
                amfi_code,
                MAX(nav_date) AS last_date
            FROM nav_history
            GROUP BY amfi_code
        ),
        latest_nav AS (
            SELECT
                l.amfi_code,
                l.last_date,
                h.nav AS last_nav
            FROM latest l
            JOIN nav_history h
              ON h.amfi_code = l.amfi_code
             AND h.nav_date  = l.last_date
        )
        SELECT
            ln.amfi_code,
            CASE
                WHEN nav_1y IS NULL OR nav_1y = 0 THEN NULL
                ELSE ((ln.last_nav / nav_1y) - 1) * 100
            END AS returns_1y,
            CASE
                WHEN nav_3y IS NULL OR nav_3y = 0 THEN NULL
                ELSE (POWER(ln.last_nav / nav_3y, 1.0 / 3) - 1) * 100
            END AS returns_3y,
            CASE
                WHEN nav_5y IS NULL OR nav_5y = 0 THEN NULL
                ELSE (POWER(ln.last_nav / nav_5y, 1.0 / 5) - 1) * 100
            END AS returns_5y,
            CURRENT_TIMESTAMP AS last_computed_at
        FROM latest_nav ln
        LEFT JOIN LATERAL (
            SELECT h.nav
            FROM nav_history h
            WHERE h.amfi_code = ln.amfi_code
              AND ABS(date_diff('day', h.nav_date, ln.last_date - INTERVAL 1 YEAR)) <= 30
            ORDER BY ABS(date_diff('day', h.nav_date, ln.last_date - INTERVAL 1 YEAR)) ASC
            LIMIT 1
        ) AS n1y(nav_1y) ON TRUE
        LEFT JOIN LATERAL (
            SELECT h.nav
            FROM nav_history h
            WHERE h.amfi_code = ln.amfi_code
              AND ABS(date_diff('day', h.nav_date, ln.last_date - INTERVAL 3 YEAR)) <= 60
            ORDER BY ABS(date_diff('day', h.nav_date, ln.last_date - INTERVAL 3 YEAR)) ASC
            LIMIT 1
        ) AS n3y(nav_3y) ON TRUE
        LEFT JOIN LATERAL (
            SELECT h.nav
            FROM nav_history h
            WHERE h.amfi_code = ln.amfi_code
              AND ABS(date_diff('day', h.nav_date, ln.last_date - INTERVAL 5 YEAR)) <= 90
            ORDER BY ABS(date_diff('day', h.nav_date, ln.last_date - INTERVAL 5 YEAR)) ASC
            LIMIT 1
        ) AS n5y(nav_5y) ON TRUE
        """
    )
    return conn.execute("SELECT COUNT(*) FROM fund_returns").fetchone()[0]


# --------------------------------------------------------------------------- #
# Download / orchestration
# --------------------------------------------------------------------------- #


async def download_dataset(target_dir: Path) -> tuple[Path, Path]:
    """Download the schemes CSV and NAV history parquet into ``target_dir``.

    Uses ``follow_redirects=True`` (GitHub LFS serves a redirect) and a
    generous 300s timeout.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    csv_path = target_dir / "mutual_fund_data.csv"
    parquet_path = target_dir / "mutual_fund_nav_history.parquet"

    async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
        csv_resp = await client.get(SCHEMES_CSV_URL)
        csv_resp.raise_for_status()
        csv_path.write_bytes(csv_resp.content)

        nav_resp = await client.get(NAV_PARQUET_URL)
        nav_resp.raise_for_status()
        parquet_path.write_bytes(nav_resp.content)

    return csv_path, parquet_path


async def refresh(conn: duckdb.DuckDBPyConnection, data_dir: Path) -> dict:
    """Run the full ingest pipeline: download -> load -> returns -> log."""
    csv_path, parquet_path = await download_dataset(data_dir)
    scheme_count = load_schemes(conn, csv_path)
    nav_count = load_nav_history(conn, parquet_path)
    returns_count = compute_returns(conn)
    log_refresh(conn, scheme_count=scheme_count, nav_count=nav_count)
    return {
        "scheme_count": scheme_count,
        "nav_count": nav_count,
        "returns_count": returns_count,
    }


# --------------------------------------------------------------------------- #
# Enrichment (runtime-offline: only touched during refresh)
# --------------------------------------------------------------------------- #


async def enrich_universe_with_expense_ratios(
    conn: duckdb.DuckDBPyConnection,
) -> dict:
    """Enrich fund_universe rows with expense ratios from mfdata.in.

    For each curated fund, call the live API and extract expense_ratio.
    On failure, fall back to the category-typical value. This runs once
    per refresh and is the only time mfdata.in is touched.
    """
    from subprime.data.client import MFDataClient
    from subprime.data.universe import typical_expense_ratio

    rows = conn.execute(
        "SELECT amfi_code, category FROM fund_universe WHERE expense_ratio IS NULL"
    ).fetchall()

    if not rows:
        return {"enriched": 0, "fallback": 0}

    sem = asyncio.Semaphore(10)
    enriched = 0
    fallback = 0

    async with MFDataClient() as client:
        async def _fetch(code: str, category: str) -> tuple[str, float, bool]:
            async with sem:
                try:
                    details = await client.get_fund_details(code)
                    if details.expense_ratio is not None and details.expense_ratio > 0:
                        return code, details.expense_ratio, True
                except httpx.HTTPError:
                    pass
                except Exception as exc:
                    logger.warning("enrich %s failed: %s", code, exc)
                return code, typical_expense_ratio(category), False

        tasks = [_fetch(code, cat) for code, cat in rows]
        results = await asyncio.gather(*tasks)

    for code, er, is_live in results:
        conn.execute(
            "UPDATE fund_universe SET expense_ratio = ? WHERE amfi_code = ?",
            [er, code],
        )
        if is_live:
            enriched += 1
        else:
            fallback += 1

    return {"enriched": enriched, "fallback": fallback}
