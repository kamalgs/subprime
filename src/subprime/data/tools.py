"""PydanticAI tool functions for mutual fund data lookup.

Plain async functions registered on the advisor agent. Each docstring is
exposed to the LLM as the tool description.

- search_funds_universe: queries the curated DuckDB universe (offline, fast)
- get_fund_performance: hits mfdata.in for real-time NAV/details
- compare_funds: real-time multi-fund comparison via mfdata.in
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from subprime.core.config import DB_PATH
from subprime.core.models import MutualFund
from subprime.data.client import MFDataClient


def _db_path() -> Path:
    """Return the current DuckDB path. Indirection for test monkeypatching."""
    return DB_PATH


async def search_funds_universe(
    category: Optional[str] = None,
    limit: int = 20,
) -> list[MutualFund]:
    """Search the curated Indian mutual fund universe by category.

    The universe contains the top funds per category ranked by 5-year CAGR,
    including computed 1y/3y/5y returns and AUM. This is the primary way to
    discover funds when building a plan — fast, offline, grounded in history.

    Args:
        category: One of "Large Cap", "Large & Mid Cap", "Mid Cap", "Small Cap",
                  "Flexi Cap", "Multi Cap", "ELSS", "Index", "Hybrid", "Debt", "Gold".
                  None returns funds from all categories.
        limit: Max number of funds to return (default 20).

    Returns:
        List of MutualFund objects with computed returns. NAV will be 0 —
        call get_fund_performance(amfi_code) for the current live NAV.
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


async def get_fund_performance(amfi_code: str) -> MutualFund:
    """Get live real-time data for a specific mutual fund by AMFI code.

    Use this to verify current NAV, expense ratio, and latest details before
    finalizing a fund recommendation. Hits the live mfdata.in API.

    Args:
        amfi_code: The AMFI registration number (e.g. "119551").

    Returns:
        A MutualFund with the latest available data from the API.

    Raises:
        httpx.HTTPStatusError: If the fund is not found.
    """
    async with MFDataClient() as client:
        details = await client.get_fund_details(amfi_code)
        return MFDataClient.details_to_mutual_fund(details)


async def compare_funds(amfi_codes: list[str]) -> list[MutualFund]:
    """Compare multiple mutual funds side by side using live data.

    Fetches detailed data for each fund via mfdata.in so you can compare
    NAV, expense ratios, AUM, and ratings across schemes.

    Args:
        amfi_codes: List of AMFI registration numbers to compare.

    Returns:
        List of MutualFund objects, one per code, in the same order.
    """
    if not amfi_codes:
        return []
    async with MFDataClient() as client:

        async def _fetch(code: str) -> MutualFund:
            details = await client.get_fund_details(code)
            return MFDataClient.details_to_mutual_fund(details)

        return list(await asyncio.gather(*[_fetch(c) for c in amfi_codes]))
