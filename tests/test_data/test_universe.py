"""Tests for the fund universe curation module."""

from __future__ import annotations

import duckdb
import pytest

from subprime.core.models import MutualFund
from subprime.data import store, universe


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


@pytest.fixture
def conn():
    """In-memory DuckDB connection with schema applied."""
    connection = duckdb.connect(":memory:")
    store.ensure_schema(connection)
    yield connection
    connection.close()


def _populate(conn, rows):
    """Insert rows into schemes + fund_returns.

    rows: list of (amfi, name, amc, raw_category, aum, r1y, r3y, r5y)
    """
    for r in rows:
        conn.execute(
            "INSERT INTO schemes (amfi_code, name, amc, scheme_category, average_aum_cr) "
            "VALUES (?, ?, ?, ?, ?)",
            [r[0], r[1], r[2], r[3], r[4]],
        )
        conn.execute(
            "INSERT INTO fund_returns (amfi_code, returns_1y, returns_3y, returns_5y, last_computed_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [r[0], r[5], r[6], r[7]],
        )


# --------------------------------------------------------------------------- #
# normalize_category
# --------------------------------------------------------------------------- #


class TestNormalizeCategory:
    def test_large_cap(self):
        assert universe.normalize_category("Equity Scheme - Large Cap Fund") == "Large Cap"

    def test_mid_cap(self):
        assert universe.normalize_category("Equity Scheme - Mid Cap Fund") == "Mid Cap"

    def test_index(self):
        assert universe.normalize_category("Other Scheme - Index Fund") == "Index"

    def test_elss(self):
        assert universe.normalize_category("Equity Scheme - ELSS") == "ELSS"

    def test_flexi_cap(self):
        assert universe.normalize_category("Equity Scheme - Flexi Cap Fund") == "Flexi Cap"

    def test_large_and_mid_cap(self):
        assert (
            universe.normalize_category("Equity Scheme - Large & Mid Cap Fund")
            == "Large & Mid Cap"
        )

    def test_small_cap(self):
        assert universe.normalize_category("Equity Scheme - Small Cap Fund") == "Small Cap"

    def test_hybrid_aggressive(self):
        assert (
            universe.normalize_category("Hybrid Scheme - Aggressive Hybrid Fund") == "Hybrid"
        )

    def test_debt_gilt(self):
        assert universe.normalize_category("Debt Scheme - Gilt Fund") == "Debt"

    def test_gold(self):
        assert universe.normalize_category("Other Scheme - Gold ETF") == "Gold"

    def test_unmatched_returns_none(self):
        assert universe.normalize_category("Something Random") is None

    def test_none_input(self):
        assert universe.normalize_category(None) is None


# --------------------------------------------------------------------------- #
# build_universe
# --------------------------------------------------------------------------- #


class TestBuildUniverse:
    def test_top_n_per_category(self, conn):
        _populate(
            conn,
            [
                ("1", "Alpha Large Cap Fund", "AMC1", "Equity Scheme - Large Cap Fund", 5000.0, 10.0, 12.0, 15.0),
                ("2", "Beta Large Cap Fund", "AMC2", "Equity Scheme - Large Cap Fund", 4000.0, 9.0, 11.0, 14.0),
                ("3", "Gamma Large Cap Fund", "AMC3", "Equity Scheme - Large Cap Fund", 3000.0, 8.0, 10.0, 13.0),
            ],
        )
        count = universe.build_universe(conn, top_n_per_category=2)
        assert count == 2
        rows = conn.execute(
            "SELECT amfi_code, rank_in_category FROM fund_universe ORDER BY rank_in_category"
        ).fetchall()
        assert [r[0] for r in rows] == ["1", "2"]
        assert [r[1] for r in rows] == [1, 2]

    def test_multiple_categories(self, conn):
        _populate(
            conn,
            [
                ("1", "Alpha Large Cap Fund", "AMC1", "Equity Scheme - Large Cap Fund", 5000.0, 10.0, 12.0, 15.0),
                ("2", "Beta Mid Cap Fund", "AMC2", "Equity Scheme - Mid Cap Fund", 4000.0, 11.0, 13.0, 16.0),
                ("3", "Gamma Index Fund", "AMC3", "Equity Scheme - Index Fund", 3000.0, 9.0, 11.0, 13.0),
            ],
        )
        count = universe.build_universe(conn)
        assert count == 3
        rows = conn.execute(
            "SELECT DISTINCT category FROM fund_universe ORDER BY category"
        ).fetchall()
        categories = {r[0] for r in rows}
        assert categories == {"Large Cap", "Mid Cap", "Index"}

    def test_excludes_uncategorized(self, conn):
        _populate(
            conn,
            [
                ("1", "Alpha Large Cap Fund", "AMC1", "Equity Scheme - Large Cap Fund", 5000.0, 10.0, 12.0, 15.0),
                ("2", "Weird Fund", "AMC2", "Something Unknown", 4000.0, 11.0, 13.0, 16.0),
            ],
        )
        count = universe.build_universe(conn)
        assert count == 1
        rows = conn.execute("SELECT amfi_code FROM fund_universe").fetchall()
        assert [r[0] for r in rows] == ["1"]

    def test_excludes_idcw_and_dividend(self, conn):
        _populate(
            conn,
            [
                ("1", "Alpha Large Cap Fund Growth", "AMC1", "Equity Scheme - Large Cap Fund", 5000.0, 10.0, 12.0, 15.0),
                ("2", "Alpha Large Cap Fund IDCW", "AMC1", "Equity Scheme - Large Cap Fund", 5000.0, 10.0, 12.0, 15.0),
                ("3", "Alpha Large Cap Fund Dividend Payout", "AMC1", "Equity Scheme - Large Cap Fund", 5000.0, 10.0, 12.0, 15.0),
            ],
        )
        count = universe.build_universe(conn)
        assert count == 1
        rows = conn.execute("SELECT amfi_code FROM fund_universe").fetchall()
        assert [r[0] for r in rows] == ["1"]

    def test_rebuild_replaces(self, conn):
        _populate(
            conn,
            [
                ("1", "Alpha Large Cap Fund", "AMC1", "Equity Scheme - Large Cap Fund", 5000.0, 10.0, 12.0, 15.0),
            ],
        )
        universe.build_universe(conn)
        count_after_second = universe.build_universe(conn)
        assert count_after_second == 1
        rows = conn.execute("SELECT COUNT(*) FROM fund_universe").fetchone()
        assert rows[0] == 1


# --------------------------------------------------------------------------- #
# render_universe_context
# --------------------------------------------------------------------------- #


class TestRenderUniverseContext:
    def test_includes_category_headers(self, conn):
        _populate(
            conn,
            [
                ("1", "Alpha Large Cap Fund", "AMC One", "Equity Scheme - Large Cap Fund", 5000.0, 10.5, 12.3, 15.1),
                ("2", "Beta Mid Cap Fund", "AMC Two", "Equity Scheme - Mid Cap Fund", 4000.0, 11.2, 13.4, 16.0),
            ],
        )
        universe.build_universe(conn)
        md = universe.render_universe_context(conn)
        assert "Curated Fund Universe" in md
        assert "### Large Cap" in md
        assert "### Mid Cap" in md
        assert "Alpha Large Cap Fund" in md
        assert "Beta Mid Cap Fund" in md
        assert "AMC One" in md
        # returns formatted as percentages
        assert "15.1%" in md or "15.10%" in md

    def test_skips_empty_categories(self, conn):
        _populate(
            conn,
            [
                ("1", "Alpha Large Cap Fund", "AMC One", "Equity Scheme - Large Cap Fund", 5000.0, 10.5, 12.3, 15.1),
            ],
        )
        universe.build_universe(conn)
        md = universe.render_universe_context(conn)
        assert "### Large Cap" in md
        # No Mid Cap header since no mid cap funds
        assert "### Mid Cap" not in md

    def test_empty_universe_returns_placeholder(self, conn):
        md = universe.render_universe_context(conn)
        assert isinstance(md, str)
        assert len(md) > 0
        assert "No curated fund universe" in md


# --------------------------------------------------------------------------- #
# search_universe
# --------------------------------------------------------------------------- #


class TestSearchUniverse:
    def test_filter_by_category(self, conn):
        _populate(
            conn,
            [
                ("1", "Alpha Large Cap Fund", "AMC One", "Equity Scheme - Large Cap Fund", 5000.0, 10.5, 12.3, 15.1),
                ("2", "Beta Mid Cap Fund", "AMC Two", "Equity Scheme - Mid Cap Fund", 4000.0, 11.2, 13.4, 16.0),
            ],
        )
        universe.build_universe(conn)
        results = universe.search_universe(conn, category="Large Cap")
        assert len(results) == 1
        assert isinstance(results[0], MutualFund)
        assert results[0].amfi_code == "1"
        assert results[0].category == "Large Cap"
        assert results[0].fund_house == "AMC One"
        assert results[0].returns_5y == pytest.approx(15.1)
        assert results[0].aum_cr == pytest.approx(5000.0)

    def test_no_filter_returns_all(self, conn):
        _populate(
            conn,
            [
                ("1", "Alpha Large Cap Fund", "AMC One", "Equity Scheme - Large Cap Fund", 5000.0, 10.5, 12.3, 15.1),
                ("2", "Beta Mid Cap Fund", "AMC Two", "Equity Scheme - Mid Cap Fund", 4000.0, 11.2, 13.4, 16.0),
            ],
        )
        universe.build_universe(conn)
        results = universe.search_universe(conn)
        assert len(results) == 2
        assert all(isinstance(r, MutualFund) for r in results)

    def test_limit_applied(self, conn):
        _populate(
            conn,
            [
                ("1", "Alpha Large Cap Fund", "AMC1", "Equity Scheme - Large Cap Fund", 5000.0, 10.0, 12.0, 15.0),
                ("2", "Beta Large Cap Fund", "AMC2", "Equity Scheme - Large Cap Fund", 4000.0, 9.0, 11.0, 14.0),
                ("3", "Gamma Large Cap Fund", "AMC3", "Equity Scheme - Large Cap Fund", 3000.0, 8.0, 10.0, 13.0),
            ],
        )
        universe.build_universe(conn)
        results = universe.search_universe(conn, category="Large Cap", limit=2)
        assert len(results) == 2

    def test_empty_returns_empty_list(self, conn):
        results = universe.search_universe(conn)
        assert results == []


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


class TestCuratedCategoriesConstant:
    def test_expected_categories(self):
        for name in ("Large Cap", "Mid Cap", "Index", "ELSS"):
            assert name in universe.CURATED_CATEGORIES
