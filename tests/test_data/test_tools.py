"""Tests for subprime.data.tools — PydanticAI tool functions.

Google-style small tests: fast, deterministic, no real network calls.
Uses respx to mock httpx requests.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from subprime.core.models import MutualFund

BASE = "https://mfdata.in/api/v1"

# ---------------------------------------------------------------------------
# Fixtures — realistic mfdata.in API v1 response shapes
# ---------------------------------------------------------------------------

SEARCH_RESPONSE = {
    "status": "success",
    "data": [
        {
            "amfi_code": "119551",
            "name": "UTI Nifty 50 Index Fund - Direct Plan - Growth",
            "category": "Large-Cap",
            "plan_type": "direct",
            "option_type": "growth",
            "nav": 150.25,
            "nav_date": "2026-04-07",
            "expense_ratio": 0.10,
            "aum": 150000000000.0,
            "morningstar": 4,
            "risk_label": "Very High Risk",
            "family_name": "UTI Nifty 50 Index Fund",
            "amc_name": "UTI Mutual Fund",
            "amc_slug": "uti-mutual-fund",
        },
        {
            "amfi_code": "120505",
            "name": "HDFC Index Fund - Nifty 50 Plan - Direct Plan",
            "category": "Large-Cap",
            "plan_type": "direct",
            "option_type": "growth",
            "nav": 185.60,
            "nav_date": "2026-04-07",
            "expense_ratio": 0.20,
            "aum": 120000000000.0,
            "morningstar": 3,
            "risk_label": "Very High Risk",
            "family_name": "HDFC Index Fund",
            "amc_name": "HDFC Mutual Fund",
            "amc_slug": "hdfc-mutual-fund",
        },
    ],
    "meta": {"total": 2, "limit": 100, "offset": 0},
}

DETAILS_RESPONSE_119551 = {
    "status": "success",
    "data": {
        "amfi_code": "119551",
        "name": "UTI Nifty 50 Index Fund - Direct Plan - Growth",
        "category": "Large-Cap",
        "plan_type": "direct",
        "option_type": "growth",
        "nav": 150.25,
        "nav_date": "2026-04-07",
        "expense_ratio": 0.10,
        "aum": 150000000000.0,
        "morningstar": 4,
        "amc_name": "UTI Mutual Fund",
    },
    "meta": {"cache_hit": False},
}

DETAILS_RESPONSE_120505 = {
    "status": "success",
    "data": {
        "amfi_code": "120505",
        "name": "HDFC Index Fund - Nifty 50 Plan - Direct Plan",
        "category": "Large-Cap",
        "plan_type": "direct",
        "option_type": "growth",
        "nav": 185.60,
        "nav_date": "2026-04-07",
        "expense_ratio": 0.20,
        "aum": 120000000000.0,
        "morningstar": 3,
        "amc_name": "HDFC Mutual Fund",
    },
    "meta": {"cache_hit": False},
}


# ---------------------------------------------------------------------------
# search_funds tool
# ---------------------------------------------------------------------------


class TestSearchFundsTool:
    @respx.mock
    async def test_search_funds_returns_mutual_funds(self):
        from subprime.data.tools import search_funds

        respx.get(f"{BASE}/schemes", params={"q": "nifty 50"}).mock(
            return_value=httpx.Response(200, json=SEARCH_RESPONSE)
        )

        results = await search_funds("nifty 50")

        assert len(results) == 2
        assert all(isinstance(r, MutualFund) for r in results)
        assert results[0].amfi_code == "119551"
        assert results[0].nav == 150.25
        assert results[1].amfi_code == "120505"

    @respx.mock
    async def test_search_funds_with_category(self):
        from subprime.data.tools import search_funds

        respx.get(
            f"{BASE}/schemes",
            params={"q": "nifty", "category": "Equity"},
        ).mock(return_value=httpx.Response(200, json={
            "status": "success", "data": SEARCH_RESPONSE["data"][:1]
        }))

        results = await search_funds("nifty", category="Equity")

        assert len(results) == 1

    @respx.mock
    async def test_search_funds_empty_results(self):
        from subprime.data.tools import search_funds

        respx.get(
            f"{BASE}/schemes", params={"q": "nonexistent_xyz"}
        ).mock(return_value=httpx.Response(200, json={"status": "success", "data": []}))

        results = await search_funds("nonexistent_xyz")

        assert results == []


# ---------------------------------------------------------------------------
# get_fund_performance tool
# ---------------------------------------------------------------------------


class TestGetFundPerformanceTool:
    @respx.mock
    async def test_get_fund_performance_happy_path(self):
        from subprime.data.tools import get_fund_performance

        respx.get(f"{BASE}/schemes/119551").mock(
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

        respx.get(f"{BASE}/schemes/999999").mock(
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

        respx.get(f"{BASE}/schemes/119551").mock(
            return_value=httpx.Response(200, json=DETAILS_RESPONSE_119551)
        )
        respx.get(f"{BASE}/schemes/120505").mock(
            return_value=httpx.Response(200, json=DETAILS_RESPONSE_120505)
        )

        results = await compare_funds(["119551", "120505"])

        assert len(results) == 2
        assert all(isinstance(r, MutualFund) for r in results)
        assert results[0].amfi_code == "119551"
        assert results[1].amfi_code == "120505"

    @respx.mock
    async def test_compare_funds_empty_list(self):
        from subprime.data.tools import compare_funds

        results = await compare_funds([])

        assert results == []
