"""PydanticAI tool functions for mutual fund data lookup.

Plain async functions registered on the advisor agent. Each docstring is
exposed to the LLM as the tool description.

All tools read from the local DuckDB curated universe — no network calls
happen at plan-generation time. Expense ratios are populated once, during
``subprime data refresh``, via :func:`subprime.data.ingest.enrich_universe_with_expense_ratios`.

- search_funds_universe: queries the curated DuckDB universe by category
- get_fund_details: looks up a single fund by AMFI code from DuckDB
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from subprime.core.config import DB_PATH
from subprime.core.models import MutualFund

logger = logging.getLogger(__name__)


def _db_path() -> Path:
    """Return the current DuckDB path. Indirection for test monkeypatching."""
    return DB_PATH


async def search_funds_universe(
    category: Optional[str] = None,
    limit: int = 20,
) -> list[MutualFund]:
    """Search the curated Indian mutual fund universe by category.

    The universe contains the top funds per category ranked by 5-year CAGR,
    including computed 1y/3y/5y returns, AUM, and expense ratio. This is the
    primary way to discover funds when building a plan — fast, offline,
    grounded in history.

    Args:
        category: One of "Large Cap", "Large & Mid Cap", "Mid Cap", "Small Cap",
                  "Flexi Cap", "Multi Cap", "ELSS", "Index", "Aggressive Hybrid",
                  "Conservative Hybrid", "Debt", "Gold".
                  None returns funds from all categories.
        limit: Max number of funds to return (default 20).

    Returns:
        List of MutualFund objects with computed returns and expense ratio.
        NAV is 0 — the curated universe does not track live NAV.
    """
    import duckdb

    from subprime.data.universe import search_universe

    path = _db_path()
    if not path.exists():
        return []
    conn = duckdb.connect(str(path), read_only=True)
    try:
        return search_universe(conn, category=category, limit=limit)
    finally:
        conn.close()


async def get_fund_details(amfi_code: str) -> MutualFund | None:
    """Get details for a specific mutual fund by AMFI code.

    Reads from the curated fund universe in DuckDB. Use this when you have
    a specific fund code and need its full details (returns, AUM, expense ratio).

    Args:
        amfi_code: The AMFI registration number (e.g. "119551").

    Returns:
        A MutualFund object, or None if the code is not in the curated universe.
    """
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
