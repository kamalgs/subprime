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

DETAILS_RESPONSE = {
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

DETAILS_MINIMAL_RESPONSE = {
    "amfi_code": "119551",
    "name": "UTI Nifty 50 Index Fund - Direct Plan - Growth",
    "category": "Equity",
    "sub_category": "Large Cap",
    "fund_house": "UTI Mutual Fund",
    "nav": 150.25,
}

NAV_HISTORY_RESPONSE = [
    {"date": "2026-04-07", "nav": 150.25},
    {"date": "2026-04-06", "nav": 149.80},
    {"date": "2026-04-05", "nav": 148.90},
]


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchemeSearchResult:
    def test_construction(self):
        result = SchemeSearchResult(**SEARCH_RESPONSE[0])
        assert result.amfi_code == "119551"
        assert result.name == "UTI Nifty 50 Index Fund - Direct Plan - Growth"
        assert result.category == "Equity"
        assert result.sub_category == "Large Cap"
        assert result.fund_house == "UTI Mutual Fund"


class TestSchemeDetails:
    def test_construction_full(self):
        details = SchemeDetails(**DETAILS_RESPONSE)
        assert details.amfi_code == "119551"
        assert details.nav == 150.25
        assert details.nav_date == "2026-04-07"
        assert details.expense_ratio == 0.10
        assert details.aum_cr == 15000.5
        assert details.morningstar == 4

    def test_construction_minimal(self):
        details = SchemeDetails(**DETAILS_MINIMAL_RESPONSE)
        assert details.nav_date is None
        assert details.expense_ratio is None
        assert details.aum_cr is None
        assert details.morningstar is None


# ---------------------------------------------------------------------------
# Conversion: SchemeDetails -> MutualFund
# ---------------------------------------------------------------------------


class TestDetailsToMutualFund:
    def test_full_details(self):
        from subprime.data.client import MFDataClient

        details = SchemeDetails(**DETAILS_RESPONSE)
        fund = MFDataClient.details_to_mutual_fund(details)
        assert isinstance(fund, MutualFund)
        assert fund.amfi_code == "119551"
        assert fund.name == "UTI Nifty 50 Index Fund - Direct Plan - Growth"
        assert fund.category == "Equity"
        assert fund.sub_category == "Large Cap"
        assert fund.fund_house == "UTI Mutual Fund"
        assert fund.nav == 150.25
        assert fund.expense_ratio == 0.10
        assert fund.aum_cr == 15000.5
        assert fund.morningstar_rating == 4

    def test_minimal_details(self):
        from subprime.data.client import MFDataClient

        details = SchemeDetails(**DETAILS_MINIMAL_RESPONSE)
        fund = MFDataClient.details_to_mutual_fund(details)
        assert isinstance(fund, MutualFund)
        assert fund.expense_ratio == 0.0  # default when missing
        assert fund.aum_cr is None
        assert fund.morningstar_rating is None


# ---------------------------------------------------------------------------
# Client HTTP tests (respx-mocked)
# ---------------------------------------------------------------------------


class TestMFDataClientSearch:
    @respx.mock
    async def test_search_funds_happy_path(self):
        from subprime.data.client import MFDataClient

        respx.get("https://api.mfdata.in/mf/search", params={"q": "nifty 50"}).mock(
            return_value=httpx.Response(200, json=SEARCH_RESPONSE)
        )

        async with MFDataClient() as client:
            results = await client.search_funds("nifty 50")

        assert len(results) == 2
        assert all(isinstance(r, SchemeSearchResult) for r in results)
        assert results[0].amfi_code == "119551"
        assert results[1].amfi_code == "120505"

    @respx.mock
    async def test_search_funds_with_category(self):
        from subprime.data.client import MFDataClient

        respx.get(
            "https://api.mfdata.in/mf/search",
            params={"q": "nifty", "category": "Equity"},
        ).mock(return_value=httpx.Response(200, json=SEARCH_RESPONSE[:1]))

        async with MFDataClient() as client:
            results = await client.search_funds("nifty", category="Equity")

        assert len(results) == 1
        assert results[0].category == "Equity"

    @respx.mock
    async def test_search_funds_empty_results(self):
        from subprime.data.client import MFDataClient

        respx.get("https://api.mfdata.in/mf/search", params={"q": "nonexistent_xyz"}).mock(
            return_value=httpx.Response(200, json=[])
        )

        async with MFDataClient() as client:
            results = await client.search_funds("nonexistent_xyz")

        assert results == []


class TestMFDataClientDetails:
    @respx.mock
    async def test_get_fund_details_happy_path(self):
        from subprime.data.client import MFDataClient

        respx.get("https://api.mfdata.in/mf/119551").mock(
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

        respx.get("https://api.mfdata.in/mf/999999").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )

        async with MFDataClient() as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_fund_details("999999")

    @respx.mock
    async def test_get_fund_details_missing_optional_fields(self):
        from subprime.data.client import MFDataClient

        respx.get("https://api.mfdata.in/mf/119551").mock(
            return_value=httpx.Response(200, json=DETAILS_MINIMAL_RESPONSE)
        )

        async with MFDataClient() as client:
            details = await client.get_fund_details("119551")

        assert details.expense_ratio is None
        assert details.aum_cr is None
        assert details.morningstar is None


class TestMFDataClientNavHistory:
    @respx.mock
    async def test_get_nav_history_happy_path(self):
        from subprime.data.client import MFDataClient

        respx.get("https://api.mfdata.in/mf/119551/nav").mock(
            return_value=httpx.Response(200, json=NAV_HISTORY_RESPONSE)
        )

        async with MFDataClient() as client:
            history = await client.get_nav_history("119551")

        assert len(history) == 3
        assert history[0]["date"] == "2026-04-07"
        assert history[0]["nav"] == 150.25

    @respx.mock
    async def test_get_nav_history_404(self):
        from subprime.data.client import MFDataClient

        respx.get("https://api.mfdata.in/mf/999999/nav").mock(
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
            "http://localhost:8080/mf/search", params={"q": "nifty"}
        ).mock(return_value=httpx.Response(200, json=SEARCH_RESPONSE))

        async with MFDataClient(base_url="http://localhost:8080") as client:
            results = await client.search_funds("nifty")

        assert len(results) == 2
