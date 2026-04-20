"""PydanticAI tool functions for mutual fund data lookup.

Plain async functions registered on the advisor agent. Each docstring is
exposed to the LLM as the tool description.

All tools read from the local DuckDB curated universe — no network calls
happen at plan-generation time. Expense ratios are populated once, during
``subprime data refresh``, via :func:`subprime.data.ingest.enrich_universe_with_expense_ratios`.

- list_fund_categories: enumerate category names + tax regime
- search_funds_bundle:  run SEVERAL filter+order buckets in one call
- search_funds:         single filter+order bucket
- get_fund_details:     single lookup by AMFI code
- run_sql:              arbitrary read-only SQL against the curated universe
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from subprime.core.config import DB_PATH
from subprime.core.models import MutualFund

logger = logging.getLogger(__name__)


def _db_path() -> Path:
    return DB_PATH


# ---------- sync workers (run via asyncio.to_thread) ----------


def _sync_query(**kwargs) -> list[MutualFund]:
    import duckdb
    from subprime.data.universe import query_universe

    path = _db_path()
    if not path.exists():
        return []
    conn = duckdb.connect(str(path), read_only=True)
    try:
        return query_universe(conn, **kwargs)
    finally:
        conn.close()


def _sync_get_by_code(amfi_code: str) -> MutualFund | None:
    import duckdb
    from subprime.data.universe import search_universe_by_code

    path = _db_path()
    if not path.exists():
        return None
    conn = duckdb.connect(str(path), read_only=True)
    try:
        return search_universe_by_code(conn, amfi_code)
    finally:
        conn.close()


def _sync_categories() -> list[dict]:
    import duckdb
    from subprime.data.universe import CURATED_CATEGORIES, tax_regime, _TAX_LABELS

    path = _db_path()
    if not path.exists():
        return []
    conn = duckdb.connect(str(path), read_only=True)
    try:
        out = []
        for cat in CURATED_CATEGORIES:
            row = conn.execute(
                "SELECT COUNT(*) FROM fund_universe WHERE category = ?", [cat]
            ).fetchone()
            count = int(row[0]) if row else 0
            if count == 0:
                continue
            regime = tax_regime(cat)
            out.append({
                "category": cat,
                "count": count,
                "tax_regime": regime,
                "tax_note": _TAX_LABELS[regime],
            })
        return out
    finally:
        conn.close()


# ---------- advisor-facing tools ----------


OrderKey = Literal[
    "returns_5y", "returns_3y", "returns_1y",
    "expense_ratio", "aum_cr",
    "sharpe_ratio", "alpha", "beta", "tracking_error", "information_ratio",
]


async def search_funds(
    categories: Optional[list[str]] = None,
    max_expense_ratio: Optional[float] = None,
    min_aum_cr: Optional[float] = None,
    min_returns_3y: Optional[float] = None,
    min_returns_5y: Optional[float] = None,
    max_beta: Optional[float] = None,
    min_alpha: Optional[float] = None,
    max_tracking_error: Optional[float] = None,
    order_by: OrderKey = "returns_5y",
    descending: bool = True,
    limit: int = 10,
) -> list[MutualFund]:
    """Search the curated Indian mutual fund universe with flexible filters.

    Combine any filters + ordering to express the plan's needs. Examples:

    - Low-cost index for a 30-year horizon:
          categories=["Index"], max_expense_ratio=0.3, order_by="expense_ratio", descending=False
    - High-alpha active mid cap:
          categories=["Mid Cap"], min_alpha=2.0, min_returns_5y=15, order_by="alpha"
    - Tax-efficient equity wrapper for old-regime investor:
          categories=["ELSS"], min_returns_3y=12, order_by="returns_5y"
    - Conservative debt for pre-retirement investor:
          categories=["Debt"], min_aum_cr=2000, max_tracking_error=2.0, order_by="sharpe_ratio"

    Args:
        categories:          One or more category names. Valid names come from
                             list_fund_categories(). Omit to search all categories.
        max_expense_ratio:   Upper bound on yearly fee (%). Lower = cheaper.
        min_aum_cr:          Lower bound on AUM in crores. Higher = more established.
        min_returns_3y:      Minimum 3-year CAGR (%).
        min_returns_5y:      Minimum 5-year CAGR (%).
        max_beta:            Upper bound on beta vs Nifty 50 (1.0 = market-like).
        min_alpha:            Minimum Jensen's alpha (%) — positive = skill above market.
        max_tracking_error:  Upper bound on tracking error (%) — lower = index-like.
        order_by:            Column to sort by. Defaults to 5y returns (track record).
        descending:          True = best first. Set False for ascending (e.g. cheapest fee first).
        limit:               Max rows to return (default 10).

    Returns:
        List of MutualFund objects with full metadata. NAV is 0 — the curated
        universe does not track live NAV.
    """
    # DuckDB calls are synchronous; run in a worker thread so we don't block
    # uvicorn's single event loop while the query executes.
    return await asyncio.to_thread(
        _sync_query,
        categories=categories,
        max_expense_ratio=max_expense_ratio,
        min_aum_cr=min_aum_cr,
        min_returns_3y=min_returns_3y,
        min_returns_5y=min_returns_5y,
        max_beta=max_beta,
        min_alpha=min_alpha,
        max_tracking_error=max_tracking_error,
        order_by=order_by,
        descending=descending,
        limit=limit,
    )


async def get_fund_details(amfi_code: str) -> MutualFund | None:
    """Look up a single mutual fund by AMFI code.

    Use this when you already have an AMFI code (e.g. from search_funds) and
    want the full record. Reads from the curated universe.

    Args:
        amfi_code: The AMFI registration number (e.g. "119551").

    Returns:
        A MutualFund object, or None if the code is not in the curated universe.
    """
    return await asyncio.to_thread(_sync_get_by_code, amfi_code)


async def list_fund_categories() -> list[dict]:
    """List the fund categories available in the curated universe.

    Each entry includes:
      - ``category``: canonical name (pass this to search_funds)
      - ``count``: number of curated funds in this category
      - ``tax_regime``: ``equity`` / ``equity-80c`` / ``slab``
      - ``tax_note``: human-readable explanation of the tax treatment

    Call this first to orient yourself before searching. Avoids guessing
    category names.
    """
    return await asyncio.to_thread(_sync_categories)


class FundQuery(BaseModel):
    """A single named filter+order bucket for search_funds_bundle.

    Every field except ``label`` is optional. Mirrors the search_funds args.
    """
    label: str = Field(
        description="Human-readable name for this bucket, used as the key in the response (e.g. 'cheap_index', 'active_mid', 'elss')"
    )
    categories: Optional[list[str]] = None
    max_expense_ratio: Optional[float] = None
    min_aum_cr: Optional[float] = None
    min_returns_3y: Optional[float] = None
    min_returns_5y: Optional[float] = None
    max_beta: Optional[float] = None
    min_alpha: Optional[float] = None
    max_tracking_error: Optional[float] = None
    order_by: Literal[
        "returns_5y", "returns_3y", "returns_1y",
        "expense_ratio", "aum_cr",
        "sharpe_ratio", "alpha", "beta", "tracking_error", "information_ratio",
    ] = "returns_5y"
    descending: bool = True
    limit: int = 6


def _sync_query_many(queries: list[FundQuery]) -> dict[str, list[MutualFund]]:
    """Run each FundQuery against a single DuckDB connection."""
    import duckdb
    from subprime.data.universe import query_universe

    path = _db_path()
    if not path.exists():
        return {q.label: [] for q in queries}
    conn = duckdb.connect(str(path), read_only=True)
    try:
        out: dict[str, list[MutualFund]] = {}
        for q in queries:
            out[q.label] = query_universe(
                conn,
                categories=q.categories,
                max_expense_ratio=q.max_expense_ratio,
                min_aum_cr=q.min_aum_cr,
                min_returns_3y=q.min_returns_3y,
                min_returns_5y=q.min_returns_5y,
                max_beta=q.max_beta,
                min_alpha=q.min_alpha,
                max_tracking_error=q.max_tracking_error,
                order_by=q.order_by,
                descending=q.descending,
                limit=q.limit,
            )
        return out
    finally:
        conn.close()


async def search_funds_bundle(queries: list[FundQuery]) -> dict[str, list[MutualFund]]:
    """Run multiple filter+order searches in a single call.

    Use this when a plan needs funds from several distinct buckets — e.g. a
    low-cost index sleeve, a high-alpha mid-cap sleeve, and a defensive debt
    sleeve. One tool call, one DB connection, no extra round-trips.

    Each element of ``queries`` is a named bucket (``label``). The response is
    a dict mapping each label to its matching funds.

    Example (in Python — the LLM will pass the same shape as JSON):

        [
          FundQuery(label="cheap_index", categories=["Index"],
                    max_expense_ratio=0.3, order_by="expense_ratio",
                    descending=False, limit=5),
          FundQuery(label="active_mid", categories=["Mid Cap"],
                    min_alpha=2.0, min_returns_5y=15, order_by="alpha", limit=5),
          FundQuery(label="defensive_debt", categories=["Debt"],
                    min_aum_cr=2000, order_by="sharpe_ratio", limit=5),
        ]

    Prefer this over several individual ``search_funds`` calls — fewer agent
    loop iterations, lower latency, smaller prompt re-sends.
    """
    return await asyncio.to_thread(_sync_query_many, queries)


_SQL_ROW_CAP = 100


def _sync_run_sql(query: str) -> dict:
    import duckdb

    path = _db_path()
    if not path.exists():
        return {"error": "database not available", "rows": [], "columns": []}
    conn = duckdb.connect(str(path), read_only=True)
    try:
        cur = conn.execute(query)
        columns = [d[0] for d in cur.description] if cur.description else []
        raw = cur.fetchmany(_SQL_ROW_CAP + 1)
        truncated = len(raw) > _SQL_ROW_CAP
        rows = [dict(zip(columns, r)) for r in raw[:_SQL_ROW_CAP]]
        # DuckDB returns date/datetime objects; stringify anything not
        # JSON-native so the tool result serialises cleanly.
        for row in rows:
            for k, v in list(row.items()):
                if v is None or isinstance(v, (bool, int, float, str)):
                    continue
                row[k] = str(v)
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    except Exception as e:  # duckdb errors bubble up as strings the LLM can read
        return {"error": f"{type(e).__name__}: {e}", "rows": [], "columns": []}
    finally:
        conn.close()


async def run_sql(query: str) -> dict:
    """Run arbitrary read-only SQL against the curated fund universe (DuckDB).

    Use this when the typed filters in ``search_funds`` / ``search_funds_bundle``
    don't express what you need — e.g. computing a custom ratio, filtering on
    a combined condition, grouping by AMC, or joining across sleeves.

    Connection is opened ``read_only=True``: ``INSERT`` / ``UPDATE`` / ``DELETE`` /
    DDL will fail. You cannot damage the database.

    Primary table — ``fund_universe``:

        amfi_code         VARCHAR   PRIMARY KEY
        name              VARCHAR
        display_name      VARCHAR   -- short UI label
        amc               VARCHAR   -- fund house (e.g. 'HDFC', 'Parag Parikh')
        category          VARCHAR   -- canonical name, see list_fund_categories()
        sub_category      VARCHAR   -- raw AMFI category string
        aum_cr            DOUBLE    -- assets under management, ₹ crore
        launch_date       DATE
        returns_1y        DOUBLE    -- CAGR %, 1-year
        returns_3y        DOUBLE    -- CAGR %, 3-year
        returns_5y        DOUBLE    -- CAGR %, 5-year
        expense_ratio     DOUBLE    -- yearly fee %
        rank_in_category  INTEGER
        volatility_1y     DOUBLE
        beta              DOUBLE    -- vs Nifty 50
        alpha             DOUBLE    -- Jensen's alpha %
        tracking_error    DOUBLE    -- %
        sharpe_ratio      DOUBLE
        information_ratio DOUBLE

    Every row has plan_type='direct' (or is an ETF) — no regular-plan noise.

    Examples:

        -- Cheapest index funds overall
        SELECT amfi_code, name, amc, expense_ratio, returns_5y
        FROM fund_universe WHERE category = 'Index'
        ORDER BY expense_ratio ASC LIMIT 5;

        -- Mid caps with strong alpha AND reasonable fees
        SELECT amfi_code, name, amc, alpha, expense_ratio, returns_5y
        FROM fund_universe
        WHERE category = 'Mid Cap' AND alpha >= 2 AND expense_ratio <= 1.0
        ORDER BY alpha DESC LIMIT 5;

        -- AMC diversification check: top 3y performer per AMC in Flexi Cap
        SELECT amc, amfi_code, name, returns_3y
        FROM (
          SELECT *, ROW_NUMBER() OVER (PARTITION BY amc ORDER BY returns_3y DESC) rn
          FROM fund_universe WHERE category = 'Flexi Cap'
        ) WHERE rn = 1 ORDER BY returns_3y DESC LIMIT 10;

    Args:
        query: A single SELECT / CTE statement.

    Returns:
        Dict with ``columns``, ``rows`` (list of dicts), ``row_count``, and
        ``truncated`` (True if more than 100 rows matched — tighten your WHERE
        clause or add ORDER BY + LIMIT). On SQL error, returns ``error`` with
        the DuckDB message and empty rows.
    """
    return await asyncio.to_thread(_sync_run_sql, query)


# Kept for backwards compat with older callers / tests that used the
# category-only signature. Deprecated — prefer search_funds / search_funds_bundle.
async def search_funds_universe(
    category: Optional[str] = None,
    limit: int = 20,
) -> list[MutualFund]:
    """Deprecated: use ``search_funds`` or ``search_funds_bundle``. Thin back-compat wrapper."""
    cats = [category] if category else None
    return await search_funds(categories=cats, limit=limit)
