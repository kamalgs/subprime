"""Tests for strategy-scoped universe filtering."""
import pytest
import duckdb

from subprime.data.store import ensure_schema
from subprime.data.universe import (
    CURATED_CATEGORIES,
    _relevant_categories,
    render_universe_context,
)


def test_equity_only_strategy():
    cats = _relevant_categories(equity_pct=100, debt_pct=0, gold_pct=0)
    # All 8 equity sub-categories
    assert "Large Cap" in cats
    assert "Flexi Cap" in cats
    assert "ELSS" in cats
    assert "Index" in cats
    # No debt, no gold, no hybrids
    assert "Debt" not in cats
    assert "Gold" not in cats
    assert "Aggressive Hybrid" not in cats


def test_balanced_strategy_includes_hybrids():
    cats = _relevant_categories(equity_pct=70, debt_pct=20, gold_pct=10)
    assert "Large Cap" in cats
    assert "Debt" in cats
    assert "Gold" in cats
    # Hybrids only included when BOTH equity and debt are non-zero
    assert "Aggressive Hybrid" in cats
    assert "Conservative Hybrid" in cats


def test_debt_only_strategy():
    cats = _relevant_categories(equity_pct=0, debt_pct=100, gold_pct=0)
    assert "Debt" in cats
    # Equity categories excluded
    assert "Large Cap" not in cats
    assert "Small Cap" not in cats
    # No hybrids (equity is 0)
    assert "Aggressive Hybrid" not in cats


def test_gold_only_strategy():
    cats = _relevant_categories(equity_pct=0, debt_pct=0, gold_pct=100)
    assert cats == ["Gold"]


def test_all_zero_strategy_returns_empty():
    # Caller (_load_universe_context) falls back to full universe
    assert _relevant_categories(0, 0, 0) == []


def test_preserves_canonical_order():
    cats = _relevant_categories(equity_pct=50, debt_pct=30, gold_pct=20)
    # Should appear in CURATED_CATEGORIES order, not set iteration order
    indices = [CURATED_CATEGORIES.index(c) for c in cats]
    assert indices == sorted(indices)


# ------- render_universe_context with category filter -------


@pytest.fixture
def seeded_conn():
    conn = duckdb.connect(":memory:")
    ensure_schema(conn)
    # Minimal seed: one fund in each of several categories
    rows = [
        ("001", "Axis Bluechip", "Axis", "Large Cap"),
        ("002", "HDFC Nifty 50", "HDFC", "Index"),
        ("003", "SBI Short Duration", "SBI", "Debt"),
        ("004", "ICICI Gold", "ICICI", "Gold"),
    ]
    for code, name, amc, cat in rows:
        conn.execute(
            """INSERT INTO fund_universe (amfi_code, name, amc, category, rank_in_category)
               VALUES (?, ?, ?, ?, 1)""",
            [code, name, amc, cat],
        )
    yield conn
    conn.close()


def test_render_full_universe_includes_everything(seeded_conn):
    text = render_universe_context(seeded_conn)
    for name in ("Axis Bluechip", "HDFC Nifty 50", "SBI Short Duration", "ICICI Gold"):
        assert name in text


def test_render_scoped_to_equity_only(seeded_conn):
    text = render_universe_context(seeded_conn, categories=["Large Cap", "Index"])
    assert "Axis Bluechip" in text
    assert "HDFC Nifty 50" in text
    assert "SBI Short Duration" not in text
    assert "ICICI Gold" not in text


def test_render_smaller_when_scoped(seeded_conn):
    full = render_universe_context(seeded_conn)
    eq_only = render_universe_context(seeded_conn, categories=["Large Cap"])
    # Scoped render should be shorter (fewer rows, fewer category headings)
    assert len(eq_only) < len(full)
