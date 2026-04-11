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
# search_funds_universe tool
# ---------------------------------------------------------------------------


class TestSearchFundsUniverseTool:
    async def test_search_universe_by_category(self, tmp_path, monkeypatch):
        """search_funds_universe queries the local DuckDB."""
        import duckdb

        from subprime.data.store import ensure_schema
        from subprime.data.universe import build_universe

        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO schemes (amfi_code, name, amc, scheme_category, average_aum_cr) "
            "VALUES ('100', 'Test Large Cap', 'Test AMC', 'Equity Scheme - Large Cap Fund', 5000.0)"
        )
        conn.execute(
            "INSERT INTO fund_returns (amfi_code, returns_1y, returns_3y, returns_5y, last_computed_at) "
            "VALUES ('100', 10.0, 12.0, 14.0, CURRENT_TIMESTAMP)"
        )
        build_universe(conn)
        conn.close()

        monkeypatch.setattr("subprime.data.tools._db_path", lambda: db_path)

        from subprime.data.tools import search_funds_universe

        results = await search_funds_universe(category="Large Cap")
        assert len(results) == 1
        assert results[0].name == "Test Large Cap"

    async def test_search_universe_no_db(self, tmp_path, monkeypatch):
        """With no DB file, search_funds_universe returns empty list gracefully."""
        monkeypatch.setattr("subprime.data.tools._db_path", lambda: tmp_path / "nonexistent.duckdb")
        from subprime.data.tools import search_funds_universe
        results = await search_funds_universe()
        assert results == []

    async def test_search_universe_no_category_filter(self, tmp_path, monkeypatch):
        """No category filter returns funds from all categories."""
        import duckdb

        from subprime.data.store import ensure_schema
        from subprime.data.universe import build_universe

        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        ensure_schema(conn)
        for amfi, name, cat in [
            ("100", "A Large", "Equity Scheme - Large Cap Fund"),
            ("200", "A Mid", "Equity Scheme - Mid Cap Fund"),
        ]:
            conn.execute(
                "INSERT INTO schemes (amfi_code, name, amc, scheme_category, average_aum_cr) "
                "VALUES (?, ?, 'AMC', ?, 5000.0)",
                [amfi, name, cat],
            )
            conn.execute(
                "INSERT INTO fund_returns (amfi_code, returns_1y, returns_3y, returns_5y, last_computed_at) "
                "VALUES (?, 10.0, 12.0, 14.0, CURRENT_TIMESTAMP)",
                [amfi],
            )
        build_universe(conn)
        conn.close()

        monkeypatch.setattr("subprime.data.tools._db_path", lambda: db_path)
        from subprime.data.tools import search_funds_universe
        results = await search_funds_universe()
        assert len(results) == 2


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
