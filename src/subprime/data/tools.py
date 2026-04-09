"""PydanticAI tool functions for mutual fund data lookup.

These are plain async functions that PydanticAI registers as tools on the
advisor agent. Each wraps the MFDataClient internally so the LLM can query
live mutual fund data during plan generation.

Docstrings are exposed to the LLM as tool descriptions.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from subprime.core.models import MutualFund
from subprime.data.client import MFDataClient


async def search_funds(query: str, category: Optional[str] = None) -> list[MutualFund]:
    """Search for Indian mutual fund schemes by name or keyword.

    Use this to find funds matching an investment strategy. Returns basic
    fund details including NAV, expense ratio, and ratings. Results are
    capped at 10 funds.

    Args:
        query: Search term — fund name, index, or keyword (e.g. "nifty 50",
               "hdfc balanced advantage", "liquid fund").
        category: Optional category filter (e.g. "Equity", "Debt", "Hybrid").

    Returns:
        List of matching MutualFund objects with current data (max 10).
    """
    async with MFDataClient() as client:
        results = await client.search_funds(query, category=category)
        if not results:
            return []
        results = results[:10]
        # Search results from mfdata.in already include NAV, expense ratio, etc.
        return [MFDataClient.search_result_to_mutual_fund(r) for r in results]


async def get_fund_performance(amfi_code: str) -> MutualFund:
    """Get detailed data for a specific mutual fund by its AMFI code.

    Use this when you already know the exact fund and need its current NAV,
    expense ratio, AUM, and Morningstar rating.

    Args:
        amfi_code: The AMFI registration number (e.g. "119551").

    Returns:
        A MutualFund object with the latest available data.

    Raises:
        httpx.HTTPStatusError: If the fund is not found.
    """
    async with MFDataClient() as client:
        details = await client.get_fund_details(amfi_code)
        return MFDataClient.details_to_mutual_fund(details)


async def compare_funds(amfi_codes: list[str]) -> list[MutualFund]:
    """Compare multiple mutual funds side by side.

    Fetches detailed data for each fund so you can compare NAV, expense
    ratios, AUM, and ratings across schemes.

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

        funds = await asyncio.gather(*[_fetch(c) for c in amfi_codes])
        return list(funds)
