"""Tests for the DuckDB store module."""

from __future__ import annotations

import duckdb
import pytest

from subprime.data import store


EXPECTED_TABLES = {
    "schemes",
    "nav_history",
    "fund_returns",
    "fund_universe",
    "refresh_log",
}


@pytest.fixture
def conn():
    """In-memory DuckDB connection with schema applied."""
    connection = duckdb.connect(":memory:")
    store.ensure_schema(connection)
    yield connection
    connection.close()


def test_tables_exist_after_ensure_schema(conn):
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    assert EXPECTED_TABLES.issubset(table_names)


def test_ensure_schema_idempotent():
    connection = duckdb.connect(":memory:")
    store.ensure_schema(connection)
    # Should not raise on second call.
    store.ensure_schema(connection)
    rows = connection.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    assert EXPECTED_TABLES.issubset(table_names)
    connection.close()


def test_log_and_read_refresh(conn):
    store.log_refresh(conn, scheme_count=42, nav_count=1000)
    stats = store.get_refresh_stats(conn)
    assert stats is not None
    assert stats["scheme_count"] == 42
    assert stats["nav_count"] == 1000
    assert stats["refreshed_at"] is not None


def test_get_stats_empty(conn):
    assert store.get_refresh_stats(conn) is None


def test_multiple_refreshes_returns_latest(conn):
    store.log_refresh(conn, scheme_count=1, nav_count=10)
    store.log_refresh(conn, scheme_count=2, nav_count=20)
    store.log_refresh(conn, scheme_count=3, nav_count=30)
    stats = store.get_refresh_stats(conn)
    assert stats is not None
    assert stats["scheme_count"] == 3
    assert stats["nav_count"] == 30


def test_get_connection_creates_parent_directory(tmp_path):
    nested = tmp_path / "a" / "b" / "c" / "subprime.duckdb"
    assert not nested.parent.exists()
    connection = store.get_connection(nested)
    try:
        assert nested.parent.exists()
        assert nested.exists()
    finally:
        connection.close()


def test_get_connection_returns_duckdb_connection(tmp_path):
    path = tmp_path / "test.duckdb"
    connection = store.get_connection(path)
    try:
        assert isinstance(connection, duckdb.DuckDBPyConnection)
    finally:
        connection.close()
