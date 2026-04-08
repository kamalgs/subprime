"""Tests for subprime.data.tools — PydanticAI tool functions.

Google-style small tests: fast, deterministic, no real network calls.
Uses respx to mock httpx requests.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from subprime.core.models import MutualFund


# ---------------------------------------------------------------------------
# Fixtures — realistic mfdata.in API response shapes
# ---------------------------------------------------------------------------

SEARCH_RESPONSE = [
    {
        "amfi_code": "119551",
        "name": "UTI Nifty 50 Index Fund - Direct Plan - Growth",
        "category": "Equity",
        "sub_category": "Large Cap",
        "fund_house": "UTI Mutual Fund",
    },
    {
        "amfi_code": "120505",
        "name": "HDFC Index Fund - Nifty 50 Plan - Direct Plan",
        "category": "Equity",
        "sub_category": "Large Cap",
        "fund_house": "HDFC Mutual Fund",
    },
]

DETAILS_RESPONSE_119551 = {
    "amfi_code": "119551",
    "name": "UTI Nifty 50 Index Fund - Direct Plan - Growth",
    "category": "Equity",
    "sub_category": "Large Cap",
    "fund_house": "UTI Mutual Fund",
    "nav": 150.25,
    "nav_date": "2026-04-07",
    "expense_ratio": 0.10,
    "aum_cr": 15000.5,
    "morningstar": 4,
}

DETAILS_RESPONSE_120505 = {
    "amfi_code": "120505",
    "name": "HDFC Index Fund - Nifty 50 Plan - Direct Plan",
    "category": "Equity",
    "sub_category": "Large Cap",
    "fund_house": "HDFC Mutual Fund",
    "nav": 185.60,
    "nav_date": "2026-04-07",
    "expense_ratio": 0.20,
    "aum_cr": 12000.0,
    "morningstar": 3,
}


# ---------------------------------------------------------------------------
# search_funds tool
# ---------------------------------------------------------------------------


class TestSearchFundsTool:
    @respx.mock
    async def test_search_funds_returns_mutual_funds(self):
        from subprime.data.tools import search_funds

        # Mock search endpoint
        respx.get("https://api.mfdata.in/mf/search", params={"q": "nifty 50"}).mock(
            return_value=httpx.Response(200, json=SEARCH_RESPONSE)
        )
        # Mock details for each search result
        respx.get("https://api.mfdata.in/mf/119551").mock(
            return_value=httpx.Response(200, json=DETAILS_RESPONSE_119551)
        )
        respx.get("https://api.mfdata.in/mf/120505").mock(
            return_value=httpx.Response(200, json=DETAILS_RESPONSE_120505)
        )

        results = await search_funds("nifty 50")

        assert len(results) == 2
        assert all(isinstance(r, MutualFund) for r in results)
        assert results[0].amfi_code == "119551"
        assert results[0].nav == 150.25
        assert results[1].amfi_code == "120505"
        assert results[1].nav == 185.60

    @respx.mock
    async def test_search_funds_with_category(self):
        from subprime.data.tools import search_funds

        respx.get(
            "https://api.mfdata.in/mf/search",
            params={"q": "nifty", "category": "Equity"},
        ).mock(return_value=httpx.Response(200, json=SEARCH_RESPONSE[:1]))
        respx.get("https://api.mfdata.in/mf/119551").mock(
            return_value=httpx.Response(200, json=DETAILS_RESPONSE_119551)
        )

        results = await search_funds("nifty", category="Equity")

        assert len(results) == 1
        assert results[0].category == "Equity"

    @respx.mock
    async def test_search_funds_empty_results(self):
        from subprime.data.tools import search_funds

        respx.get(
            "https://api.mfdata.in/mf/search", params={"q": "nonexistent_xyz"}
        ).mock(return_value=httpx.Response(200, json=[]))

        results = await search_funds("nonexistent_xyz")

        assert results == []


# ---------------------------------------------------------------------------
# get_fund_performance tool
# ---------------------------------------------------------------------------


class TestGetFundPerformanceTool:
    @respx.mock
    async def test_get_fund_performance_happy_path(self):
        from subprime.data.tools import get_fund_performance

        respx.get("https://api.mfdata.in/mf/119551").mock(
            return_value=httpx.Response(200, json=DETAILS_RESPONSE_119551)
        )

        fund = await get_fund_performance("119551")

        assert isinstance(fund, MutualFund)
        assert fund.amfi_code == "119551"
        assert fund.nav == 150.25
        assert fund.expense_ratio == 0.10
        assert fund.morningstar_rating == 4

    @respx.mock
    async def test_get_fund_performance_404(self):
        from subprime.data.tools import get_fund_performance

        respx.get("https://api.mfdata.in/mf/999999").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            await get_fund_performance("999999")


# ---------------------------------------------------------------------------
# compare_funds tool
# ---------------------------------------------------------------------------


class TestCompareFundsTool:
    @respx.mock
    async def test_compare_funds_happy_path(self):
        from subprime.data.tools import compare_funds

        respx.get("https://api.mfdata.in/mf/119551").mock(
            return_value=httpx.Response(200, json=DETAILS_RESPONSE_119551)
        )
        respx.get("https://api.mfdata.in/mf/120505").mock(
            return_value=httpx.Response(200, json=DETAILS_RESPONSE_120505)
        )

        results = await compare_funds(["119551", "120505"])

        assert len(results) == 2
        assert all(isinstance(r, MutualFund) for r in results)
        assert results[0].amfi_code == "119551"
        assert results[1].amfi_code == "120505"

    @respx.mock
    async def test_compare_funds_single(self):
        from subprime.data.tools import compare_funds

        respx.get("https://api.mfdata.in/mf/119551").mock(
            return_value=httpx.Response(200, json=DETAILS_RESPONSE_119551)
        )

        results = await compare_funds(["119551"])

        assert len(results) == 1
        assert results[0].amfi_code == "119551"

    @respx.mock
    async def test_compare_funds_empty_list(self):
        from subprime.data.tools import compare_funds

        results = await compare_funds([])

        assert results == []
