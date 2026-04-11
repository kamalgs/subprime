"""PydanticAI tool functions for mutual fund data lookup.

Plain async functions registered on the advisor agent. Each docstring is
exposed to the LLM as the tool description.

- search_funds_universe: queries the curated DuckDB universe (offline, fast)
- get_fund_performance: hits mfdata.in for real-time NAV/details
- compare_funds: real-time multi-fund comparison via mfdata.in
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import httpx
from pydantic_ai import ModelRetry

from subprime.core.config import DB_PATH
from subprime.core.models import MutualFund
from subprime.data.client import MFDataClient

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

    Note: not every fund in the curated universe is available via the live
    API. If the lookup fails, fall back to the data already in the universe
    (returns, AUM) and pick a different fund to verify.

    Args:
        amfi_code: The AMFI registration number (e.g. "119551").

    Returns:
        A MutualFund with the latest available data from the API.
    """
    async with MFDataClient() as client:
        try:
            details = await client.get_fund_details(amfi_code)
        except httpx.HTTPStatusError as exc:
            logger.warning("get_fund_performance %s failed: %s", amfi_code, exc)
            raise ModelRetry(
                f"Live data unavailable for AMFI code {amfi_code} "
                f"(HTTP {exc.response.status_code}). "
                f"Proceed with the data from the curated universe, "
                f"or try a different fund."
            )
        except httpx.HTTPError as exc:
            logger.warning("get_fund_performance %s network error: %s", amfi_code, exc)
            raise ModelRetry(
                f"Network error fetching live data for {amfi_code}: {exc}. "
                f"Use the curated universe data for this fund."
            )
        return MFDataClient.details_to_mutual_fund(details)


async def compare_funds(amfi_codes: list[str]) -> list[MutualFund]:
    """Compare multiple mutual funds side by side using live data.

    Fetches detailed data for each fund via mfdata.in so you can compare
    NAV, expense ratios, AUM, and ratings across schemes.

    Funds that fail to resolve via live API are silently skipped — the
    comparison proceeds with whatever codes succeeded. If all lookups fail,
    returns an empty list.

    Args:
        amfi_codes: List of AMFI registration numbers to compare.

    Returns:
        List of MutualFund objects for codes that resolved successfully.
    """
    if not amfi_codes:
        return []

    async def _safe_fetch(client: MFDataClient, code: str) -> MutualFund | None:
        try:
            details = await client.get_fund_details(code)
            return MFDataClient.details_to_mutual_fund(details)
        except httpx.HTTPError as exc:
            logger.warning("compare_funds %s failed: %s", code, exc)
            return None

    async with MFDataClient() as client:
        results = await asyncio.gather(*[_safe_fetch(client, c) for c in amfi_codes])
        return [r for r in results if r is not None]
