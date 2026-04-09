"""Tests for subprime.data.client — mfdata.in HTTP client.

Google-style small tests: fast, deterministic, no real network calls.
Uses respx to mock httpx requests.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from subprime.core.models import MutualFund
from subprime.data.schemas import SchemeDetails, SchemeSearchResult

BASE = "https://mfdata.in/api/v1"

# ---------------------------------------------------------------------------
# Fixtures — realistic mfdata.in API response shapes
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
            "nav": 200.50,
            "nav_date": "2026-04-07",
            "expense_ratio": 0.20,
            "aum": 120000000000.0,
            "morningstar": 4,
            "risk_label": "Very High Risk",
            "family_name": "HDFC Index Fund",
            "amc_name": "HDFC Mutual Fund",
            "amc_slug": "hdfc-mutual-fund",
        },
    ],
    "meta": {"total": 2, "limit": 100, "offset": 0},
}

DETAILS_RESPONSE = {
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
        "risk_label": "Very High Risk",
        "family_name": "UTI Nifty 50 Index Fund",
        "amc_name": "UTI Mutual Fund",
        "amc_slug": "uti-mutual-fund",
    },
    "meta": {"cache_hit": False},
}

DETAILS_MINIMAL_RESPONSE = {
    "status": "success",
    "data": {
        "amfi_code": "119551",
        "name": "UTI Nifty 50 Index Fund - Direct Plan - Growth",
        "nav": 150.25,
    },
    "meta": {"cache_hit": False},
}

NAV_HISTORY_RESPONSE = {
    "status": "success",
    "data": {
        "amfi_code": "119551",
        "name": "UTI Nifty 50 Index Fund",
        "nav": 150.25,
        "nav_date": "2026-04-07",
    },
    "meta": {"cache_hit": False},
}


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchemeSearchResult:
    def test_construction(self):
        result = SchemeSearchResult(**SEARCH_RESPONSE["data"][0])
        assert result.amfi_code == "119551"
        assert result.name == "UTI Nifty 50 Index Fund - Direct Plan - Growth"
        assert result.category == "Large-Cap"
        assert result.fund_house == "UTI Mutual Fund"
        assert result.sub_category == "Large-Cap"

    def test_aum_cr_conversion(self):
        result = SchemeSearchResult(**SEARCH_RESPONSE["data"][0])
        assert result.aum_cr == pytest.approx(15000.0, rel=0.01)


class TestSchemeDetails:
    def test_construction_full(self):
        details = SchemeDetails(**DETAILS_RESPONSE["data"])
        assert details.amfi_code == "119551"
        assert details.nav == 150.25
        assert details.expense_ratio == 0.10
        assert details.morningstar == 4
        assert details.fund_house == "UTI Mutual Fund"

    def test_construction_minimal(self):
        details = SchemeDetails(**DETAILS_MINIMAL_RESPONSE["data"])
        assert details.expense_ratio is None
        assert details.aum is None
        assert details.morningstar is None


# ---------------------------------------------------------------------------
# Conversion: SchemeDetails -> MutualFund
# ---------------------------------------------------------------------------


class TestDetailsToMutualFund:
    def test_full_details(self):
        from subprime.data.client import MFDataClient

        details = SchemeDetails(**DETAILS_RESPONSE["data"])
        fund = MFDataClient.details_to_mutual_fund(details)
        assert isinstance(fund, MutualFund)
        assert fund.amfi_code == "119551"
        assert fund.nav == 150.25
        assert fund.expense_ratio == 0.10
        assert fund.morningstar_rating == 4

    def test_minimal_details(self):
        from subprime.data.client import MFDataClient

        details = SchemeDetails(**DETAILS_MINIMAL_RESPONSE["data"])
        fund = MFDataClient.details_to_mutual_fund(details)
        assert fund.expense_ratio == 0.0
        assert fund.aum_cr is None
        assert fund.morningstar_rating is None

    def test_morningstar_zero_returns_none(self):
        from subprime.data.client import MFDataClient

        raw = {**DETAILS_RESPONSE["data"], "morningstar": 0}
        details = SchemeDetails(**raw)
        fund = MFDataClient.details_to_mutual_fund(details)
        assert fund.morningstar_rating is None


# ---------------------------------------------------------------------------
# Client HTTP tests (respx-mocked)
# ---------------------------------------------------------------------------


class TestMFDataClientSearch:
    @respx.mock
    async def test_search_funds_happy_path(self):
        from subprime.data.client import MFDataClient

        respx.get(f"{BASE}/schemes", params={"q": "nifty 50"}).mock(
            return_value=httpx.Response(200, json=SEARCH_RESPONSE)
        )

        async with MFDataClient() as client:
            results = await client.search_funds("nifty 50")

        assert len(results) == 2
        assert all(isinstance(r, SchemeSearchResult) for r in results)
        assert results[0].amfi_code == "119551"

    @respx.mock
    async def test_search_funds_with_category(self):
        from subprime.data.client import MFDataClient

        respx.get(
            f"{BASE}/schemes",
            params={"q": "nifty", "category": "Equity"},
        ).mock(return_value=httpx.Response(200, json={
            "status": "success", "data": SEARCH_RESPONSE["data"][:1]
        }))

        async with MFDataClient() as client:
            results = await client.search_funds("nifty", category="Equity")

        assert len(results) == 1

    @respx.mock
    async def test_search_funds_empty_results(self):
        from subprime.data.client import MFDataClient

        respx.get(f"{BASE}/schemes", params={"q": "nonexistent_xyz"}).mock(
            return_value=httpx.Response(200, json={"status": "success", "data": []})
        )

        async with MFDataClient() as client:
            results = await client.search_funds("nonexistent_xyz")

        assert results == []


class TestMFDataClientDetails:
    @respx.mock
    async def test_get_fund_details_happy_path(self):
        from subprime.data.client import MFDataClient

        respx.get(f"{BASE}/schemes/119551").mock(
            return_value=httpx.Response(200, json=DETAILS_RESPONSE)
        )

        async with MFDataClient() as client:
            details = await client.get_fund_details("119551")

        assert isinstance(details, SchemeDetails)
        assert details.amfi_code == "119551"
        assert details.nav == 150.25

    @respx.mock
    async def test_get_fund_details_404(self):
        from subprime.data.client import MFDataClient

        respx.get(f"{BASE}/schemes/999999").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )

        async with MFDataClient() as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_fund_details("999999")

    @respx.mock
    async def test_get_fund_details_missing_optional_fields(self):
        from subprime.data.client import MFDataClient

        respx.get(f"{BASE}/schemes/119551").mock(
            return_value=httpx.Response(200, json=DETAILS_MINIMAL_RESPONSE)
        )

        async with MFDataClient() as client:
            details = await client.get_fund_details("119551")

        assert details.expense_ratio is None
        assert details.aum is None
        assert details.morningstar is None


class TestMFDataClientNavHistory:
    @respx.mock
    async def test_get_nav_history_happy_path(self):
        from subprime.data.client import MFDataClient

        respx.get(f"{BASE}/schemes/119551/nav").mock(
            return_value=httpx.Response(200, json=NAV_HISTORY_RESPONSE)
        )

        async with MFDataClient() as client:
            history = await client.get_nav_history("119551")

        assert len(history) >= 1

    @respx.mock
    async def test_get_nav_history_404(self):
        from subprime.data.client import MFDataClient

        respx.get(f"{BASE}/schemes/999999/nav").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )

        async with MFDataClient() as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_nav_history("999999")


class TestMFDataClientCustomBaseUrl:
    @respx.mock
    async def test_custom_base_url(self):
        from subprime.data.client import MFDataClient

        respx.get(
            "http://localhost:8080/schemes", params={"q": "nifty"}
        ).mock(return_value=httpx.Response(200, json=SEARCH_RESPONSE))

        async with MFDataClient(base_url="http://localhost:8080") as client:
            results = await client.search_funds("nifty")

        assert len(results) == 2
