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
            nav_name,
            amc,
            scheme_type,
            scheme_category,
            plan_type,
            nav,
            latest_nav_date,
            average_aum_cr,
            launch_date
        )
        SELECT
            CAST(Scheme_Code AS VARCHAR)       AS amfi_code,
            Scheme_Name                        AS name,
            Scheme_NAV_Name                    AS nav_name,
            AMC                                AS amc,
            Scheme_Type                        AS scheme_type,
            Scheme_Category                    AS scheme_category,
            CASE
                WHEN Scheme_NAV_Name ILIKE '%Direct%' THEN 'direct'
                ELSE 'regular'
            END                                AS plan_type,
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
# Risk metrics
# --------------------------------------------------------------------------- #

# Candidate AMFI codes for the Nifty 50 benchmark, in preference order.
# The first one found in the nav_history table is used.
_NIFTY50_BENCHMARK_CANDIDATES = [
    "120716",  # UTI Nifty 50 Index Fund Direct Plan
    "118834",  # HDFC Index Fund Nifty 50 Plan Direct
    "120505",  # ICICI Prudential Nifty 50 Index Fund Direct
    "120842",  # SBI Nifty Index Fund Direct
    "135781",  # Nippon India Index Fund Nifty 50 Plan Direct
]

# Indian 10-year gilt proxy for risk-free rate (annualised)
_RISK_FREE_ANNUAL = 7.0


def _find_benchmark(conn: duckdb.DuckDBPyConnection) -> str | None:
    """Return the AMFI code of the best available Nifty 50 benchmark proxy."""
    for code in _NIFTY50_BENCHMARK_CANDIDATES:
        row = conn.execute(
            "SELECT COUNT(*) FROM nav_history WHERE amfi_code = ?", [code]
        ).fetchone()
        if row and row[0] > 200:  # at least ~1 year of data
            return code

    # Fall back: find any direct Nifty 50 index fund with sufficient history
    row = conn.execute(
        """
        SELECT s.amfi_code
        FROM schemes s
        JOIN nav_history h ON h.amfi_code = s.amfi_code
        WHERE s.nav_name ILIKE '%nifty 50%'
          AND s.plan_type = 'direct'
        GROUP BY s.amfi_code
        HAVING COUNT(*) > 200
        ORDER BY COUNT(*) DESC
        LIMIT 1
        """
    ).fetchone()
    return row[0] if row else None


def compute_risk_metrics(conn: duckdb.DuckDBPyConnection) -> int:
    """Compute risk metrics for all schemes using 1-year daily NAV history.

    Metrics computed against the Nifty 50 benchmark (UTI/HDFC index fund proxy):
      - volatility_1y     : annualised std dev of daily returns (%)
      - beta              : covariance(fund, bench) / variance(bench)
      - alpha             : Jensen's alpha annualised (%)
      - tracking_error    : annualised std dev of daily excess returns (%)
      - sharpe_ratio      : (annualised_return - risk_free) / volatility
      - information_ratio : alpha / tracking_error

    Updates fund_returns in-place. Returns the number of schemes updated.
    """
    benchmark_code = _find_benchmark(conn)
    if benchmark_code is None:
        logger.warning("No Nifty 50 benchmark found — skipping risk metrics")
        return 0

    logger.info("Computing risk metrics using benchmark %s", benchmark_code)

    conn.execute(
        f"""
        UPDATE fund_returns
        SET
            volatility_1y     = metrics.volatility_1y,
            beta              = metrics.beta,
            alpha             = metrics.alpha,
            tracking_error    = metrics.tracking_error,
            sharpe_ratio      = metrics.sharpe_ratio,
            information_ratio = metrics.information_ratio
        FROM (
            WITH date_range AS (
                -- Use the most recent 1-year window available in the data
                SELECT
                    MAX(nav_date)                        AS end_date,
                    MAX(nav_date) - INTERVAL 1 YEAR      AS start_date
                FROM nav_history
                WHERE amfi_code = '{benchmark_code}'
            ),
            daily_nav AS (
                SELECT
                    amfi_code,
                    nav_date,
                    nav,
                    LAG(nav) OVER (PARTITION BY amfi_code ORDER BY nav_date) AS prev_nav
                FROM nav_history
                WHERE nav_date BETWEEN (SELECT start_date FROM date_range)
                                   AND (SELECT end_date   FROM date_range)
            ),
            daily_ret AS (
                SELECT
                    amfi_code,
                    nav_date,
                    (nav - prev_nav) / NULLIF(prev_nav, 0) AS r
                FROM daily_nav
                WHERE prev_nav IS NOT NULL
                  AND prev_nav > 0
            ),
            bench AS (
                SELECT nav_date, r AS rb
                FROM daily_ret
                WHERE amfi_code = '{benchmark_code}'
            ),
            joined AS (
                SELECT f.amfi_code, f.r AS rf, b.rb
                FROM daily_ret f
                JOIN bench b ON b.nav_date = f.nav_date
                WHERE f.amfi_code != '{benchmark_code}'
            ),
            agg AS (
                SELECT
                    amfi_code,
                    COUNT(*)                                         AS n,
                    AVG(rf)                                          AS mean_rf,
                    AVG(rb)                                          AS mean_rb,
                    STDDEV_POP(rf)                                   AS std_rf,
                    STDDEV_POP(rb)                                   AS std_rb,
                    COVAR_POP(rf, rb)                                AS cov_fb,
                    VAR_POP(rb)                                      AS var_b,
                    STDDEV_POP(rf - rb)                              AS te_daily
                FROM joined
                GROUP BY amfi_code
                HAVING COUNT(*) >= 100
            )
            SELECT
                amfi_code,
                -- Annualise daily volatility (×√252)
                std_rf * SQRT(252) * 100                             AS volatility_1y,
                -- Beta
                CASE WHEN var_b > 0 THEN cov_fb / var_b ELSE NULL END AS beta,
                -- Jensen's alpha annualised: (mean_rf - beta*mean_rb) * 252 * 100
                CASE WHEN var_b > 0
                     THEN (mean_rf - (cov_fb / var_b) * mean_rb) * 252 * 100
                     ELSE NULL END                                   AS alpha,
                -- Tracking error annualised
                te_daily * SQRT(252) * 100                           AS tracking_error,
                -- Sharpe: (annualised_return - risk_free) / volatility
                CASE WHEN std_rf > 0
                     THEN ((mean_rf * 252 * 100) - {_RISK_FREE_ANNUAL})
                          / (std_rf * SQRT(252) * 100)
                     ELSE NULL END                                   AS sharpe_ratio,
                -- Information ratio: alpha / tracking_error
                CASE WHEN te_daily > 0 AND var_b > 0
                     THEN ((mean_rf - (cov_fb / var_b) * mean_rb) * 252 * 100)
                          / (te_daily * SQRT(252) * 100)
                     ELSE NULL END                                   AS information_ratio
            FROM agg
        ) AS metrics
        WHERE fund_returns.amfi_code = metrics.amfi_code
        """
    )

    row = conn.execute("SELECT COUNT(*) FROM fund_returns WHERE beta IS NOT NULL").fetchone()
    count = int(row[0]) if row else 0
    logger.info("Risk metrics computed for %d schemes", count)
    return count


# --------------------------------------------------------------------------- #
# Download / orchestration
# --------------------------------------------------------------------------- #


async def _stream_to_file(client: httpx.AsyncClient, url: str, dest: Path) -> None:
    """Stream a remote file to disk in 1MB chunks — never buffers the whole body.

    The NAV parquet is ~500MB, so a non-streaming download would OOM a
    512MB container. This streams: peak RSS stays at the chunk size.
    """
    chunk = 1024 * 1024  # 1 MB
    tmp = dest.with_suffix(dest.suffix + ".part")
    async with client.stream("GET", url) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as f:
            async for block in resp.aiter_bytes(chunk_size=chunk):
                f.write(block)
    tmp.replace(dest)


async def download_dataset(target_dir: Path) -> tuple[Path, Path]:
    """Download the schemes CSV and NAV history parquet into ``target_dir``.

    Streams both files to disk so peak memory is bounded regardless of
    payload size. Uses ``follow_redirects=True`` (GitHub LFS serves a
    redirect) and a generous 300s timeout.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    csv_path = target_dir / "mutual_fund_data.csv"
    parquet_path = target_dir / "mutual_fund_nav_history.parquet"

    async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
        await _stream_to_file(client, SCHEMES_CSV_URL, csv_path)
        await _stream_to_file(client, NAV_PARQUET_URL, parquet_path)

    return csv_path, parquet_path


async def refresh(conn: duckdb.DuckDBPyConnection, data_dir: Path) -> dict:
    """Run the full ingest pipeline: download -> load -> returns -> risk metrics -> log."""
    csv_path, parquet_path = await download_dataset(data_dir)
    scheme_count = load_schemes(conn, csv_path)
    nav_count = load_nav_history(conn, parquet_path)
    returns_count = compute_returns(conn)
    risk_count = compute_risk_metrics(conn)
    log_refresh(conn, scheme_count=scheme_count, nav_count=nav_count)
    return {
        "scheme_count": scheme_count,
        "nav_count": nav_count,
        "returns_count": returns_count,
        "risk_metrics_count": risk_count,
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
