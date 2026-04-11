"""Tests for subprime.data.tools — PydanticAI tool functions.

All tools read from DuckDB — no network calls at runtime. Fast, deterministic.
"""

from __future__ import annotations

import duckdb
import pytest

from subprime.core.models import MutualFund
from subprime.data.store import ensure_schema
from subprime.data.universe import build_universe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_universe(db_path) -> None:
    """Seed a test DuckDB with one Large Cap fund, built into the universe."""
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
    # Simulate enrichment having run
    conn.execute(
        "UPDATE fund_universe SET expense_ratio = 0.75 WHERE amfi_code = '100'"
    )
    conn.close()


# ---------------------------------------------------------------------------
# search_funds_universe tool
# ---------------------------------------------------------------------------


class TestSearchFundsUniverseTool:
    async def test_search_universe_by_category(self, tmp_path, monkeypatch):
        """search_funds_universe queries the local DuckDB."""
        db_path = tmp_path / "test.duckdb"
        _seed_universe(db_path)

        monkeypatch.setattr("subprime.data.tools._db_path", lambda: db_path)

        from subprime.data.tools import search_funds_universe

        results = await search_funds_universe(category="Large Cap")
        assert len(results) == 1
        assert results[0].name == "Test Large Cap"
        assert results[0].expense_ratio == pytest.approx(0.75)

    async def test_search_universe_no_db(self, tmp_path, monkeypatch):
        """With no DB file, search_funds_universe returns empty list gracefully."""
        monkeypatch.setattr(
            "subprime.data.tools._db_path", lambda: tmp_path / "nonexistent.duckdb"
        )
        from subprime.data.tools import search_funds_universe

        results = await search_funds_universe()
        assert results == []

    async def test_search_universe_no_category_filter(self, tmp_path, monkeypatch):
        """No category filter returns funds from all categories."""
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
# get_fund_details tool
# ---------------------------------------------------------------------------


class TestGetFundDetailsTool:
    async def test_get_fund_details_found(self, tmp_path, monkeypatch):
        """get_fund_details returns a MutualFund for a known AMFI code."""
        db_path = tmp_path / "test.duckdb"
        _seed_universe(db_path)

        monkeypatch.setattr("subprime.data.tools._db_path", lambda: db_path)

        from subprime.data.tools import get_fund_details

        fund = await get_fund_details("100")
        assert isinstance(fund, MutualFund)
        assert fund.amfi_code == "100"
        assert fund.name == "Test Large Cap"
        assert fund.category == "Large Cap"
        assert fund.expense_ratio == pytest.approx(0.75)
        assert fund.returns_5y == pytest.approx(14.0)

    async def test_get_fund_details_not_found(self, tmp_path, monkeypatch):
        """Unknown AMFI code returns None."""
        db_path = tmp_path / "test.duckdb"
        _seed_universe(db_path)

        monkeypatch.setattr("subprime.data.tools._db_path", lambda: db_path)

        from subprime.data.tools import get_fund_details

        fund = await get_fund_details("999999")
        assert fund is None

    async def test_get_fund_details_no_db(self, tmp_path, monkeypatch):
        """No DB file → get_fund_details returns None gracefully."""
        monkeypatch.setattr(
            "subprime.data.tools._db_path", lambda: tmp_path / "nonexistent.duckdb"
        )
        from subprime.data.tools import get_fund_details

        fund = await get_fund_details("100")
        assert fund is None
