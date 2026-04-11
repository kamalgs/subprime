"""Tests for subprime.data.ingest — schemes/NAV/returns ingest pipeline.

Small deterministic tests using an in-memory DuckDB. No network calls.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from subprime.data import ingest, store


FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE_CSV = FIXTURES / "sample_schemes.csv"


@pytest.fixture
def conn():
    """In-memory DuckDB connection with schema applied."""
    connection = duckdb.connect(":memory:")
    store.ensure_schema(connection)
    yield connection
    connection.close()


# --------------------------------------------------------------------------- #
# load_schemes
# --------------------------------------------------------------------------- #


class TestLoadSchemes:
    def test_loads_fixture_csv(self, conn):
        count = ingest.load_schemes(conn, SAMPLE_CSV)
        assert count == 3

        rows = conn.execute(
            """
            SELECT amfi_code, name, amc, scheme_category
            FROM schemes
            ORDER BY amfi_code
            """
        ).fetchall()
        assert len(rows) == 3

        codes = [r[0] for r in rows]
        assert codes == ["119551", "120586", "122639"]

        by_code = {r[0]: r for r in rows}
        assert by_code["119551"][1] == "UTI Nifty 50 Index Fund - Direct Plan - Growth"
        assert by_code["119551"][2] == "UTI Mutual Fund"
        assert by_code["119551"][3] == "Equity Scheme - Index Fund"
        assert by_code["120586"][3] == "Equity Scheme - Large Cap Fund"
        assert by_code["122639"][3] == "Equity Scheme - Flexi Cap Fund"

    def test_load_schemes_is_idempotent(self, conn):
        ingest.load_schemes(conn, SAMPLE_CSV)
        count = ingest.load_schemes(conn, SAMPLE_CSV)
        assert count == 3
        total = conn.execute("SELECT COUNT(*) FROM schemes").fetchone()[0]
        assert total == 3

    def test_numeric_and_date_columns_parsed(self, conn):
        ingest.load_schemes(conn, SAMPLE_CSV)
        row = conn.execute(
            """
            SELECT nav, latest_nav_date, average_aum_cr, launch_date
            FROM schemes
            WHERE amfi_code = '119551'
            """
        ).fetchone()
        assert row[0] == pytest.approx(150.25)
        assert row[1] == date(2026, 4, 8)
        assert row[2] == pytest.approx(12000.50)
        assert row[3] == date(2013, 3, 14)


# --------------------------------------------------------------------------- #
# load_nav_history
# --------------------------------------------------------------------------- #


class TestLoadNavHistory:
    def test_loads_fixture_parquet(self, conn, tmp_path):
        parquet_path = tmp_path / "nav.parquet"

        # Build a tiny parquet via DuckDB itself — use the AMFI column shape
        # (Scheme_Code, Date, NAV) that the real dataset uses.
        build = duckdb.connect(":memory:")
        build.execute(
            """
            CREATE TABLE nav AS
            SELECT * FROM (VALUES
                ('119551', DATE '2025-04-08', 140.0),
                ('119551', DATE '2026-04-08', 150.25),
                ('120586', DATE '2025-04-08', 85.0),
                ('120586', DATE '2026-04-08', 95.40)
            ) t(Scheme_Code, Date, NAV)
            """
        )
        build.execute(f"COPY nav TO '{parquet_path}' (FORMAT PARQUET)")
        build.close()

        count = ingest.load_nav_history(conn, parquet_path)
        assert count == 4

        rows = conn.execute(
            """
            SELECT amfi_code, nav_date, nav
            FROM nav_history
            ORDER BY amfi_code, nav_date
            """
        ).fetchall()
        assert len(rows) == 4
        assert rows[0][0] == "119551"
        assert rows[0][1] == date(2025, 4, 8)
        assert rows[0][2] == pytest.approx(140.0)
        assert rows[-1][0] == "120586"
        assert rows[-1][1] == date(2026, 4, 8)
        assert rows[-1][2] == pytest.approx(95.40)

    def test_load_nav_history_replaces_existing(self, conn, tmp_path):
        parquet_path = tmp_path / "nav.parquet"
        build = duckdb.connect(":memory:")
        build.execute(
            """
            CREATE TABLE nav AS
            SELECT * FROM (VALUES
                ('119551', DATE '2026-04-08', 150.25)
            ) t(Scheme_Code, Date, NAV)
            """
        )
        build.execute(f"COPY nav TO '{parquet_path}' (FORMAT PARQUET)")
        build.close()

        ingest.load_nav_history(conn, parquet_path)
        ingest.load_nav_history(conn, parquet_path)
        total = conn.execute("SELECT COUNT(*) FROM nav_history").fetchone()[0]
        assert total == 1


# --------------------------------------------------------------------------- #
# compute_returns
# --------------------------------------------------------------------------- #


def _insert_nav(conn, amfi_code: str, rows: list[tuple[date, float]]) -> None:
    for d, nav in rows:
        conn.execute(
            "INSERT INTO nav_history (amfi_code, nav_date, nav) VALUES (?, ?, ?)",
            [amfi_code, d, nav],
        )


class TestComputeReturns:
    def test_known_cagr(self, conn):
        last = date(2026, 4, 8)
        one_year = last - timedelta(days=365)
        _insert_nav(
            conn,
            "119551",
            [
                (one_year, 100.0),
                (last, 112.0),
            ],
        )

        count = ingest.compute_returns(conn)
        assert count == 1

        row = conn.execute(
            """
            SELECT returns_1y, returns_3y, returns_5y, last_computed_at
            FROM fund_returns
            WHERE amfi_code = '119551'
            """
        ).fetchone()
        assert row is not None
        assert row[0] == pytest.approx(12.0, abs=0.5)
        assert row[1] is None
        assert row[2] is None
        assert row[3] is not None

    def test_insufficient_history_nulls(self, conn):
        last = date(2026, 4, 8)
        _insert_nav(
            conn,
            "119551",
            [
                (last - timedelta(days=14), 100.0),
                (last, 101.0),
            ],
        )

        # Should not crash.
        ingest.compute_returns(conn)

        row = conn.execute(
            """
            SELECT returns_1y, returns_3y, returns_5y
            FROM fund_returns
            WHERE amfi_code = '119551'
            """
        ).fetchone()
        # Either no row for the scheme or a row with all NULLs is acceptable.
        if row is not None:
            assert row[0] is None
            assert row[1] is None
            assert row[2] is None

    def test_compute_returns_idempotent(self, conn):
        last = date(2026, 4, 8)
        one_year = last - timedelta(days=365)
        _insert_nav(
            conn,
            "119551",
            [
                (one_year, 100.0),
                (last, 110.0),
            ],
        )

        ingest.compute_returns(conn)
        ingest.compute_returns(conn)

        total = conn.execute(
            "SELECT COUNT(*) FROM fund_returns WHERE amfi_code = '119551'"
        ).fetchone()[0]
        assert total == 1

    def test_three_year_cagr(self, conn):
        last = date(2026, 4, 8)
        three_years = last - timedelta(days=3 * 365)
        _insert_nav(
            conn,
            "119551",
            [
                (three_years, 100.0),
                (last, 133.1),  # 10% CAGR over 3 years -> 1.1^3 = 1.331
            ],
        )

        ingest.compute_returns(conn)

        row = conn.execute(
            "SELECT returns_1y, returns_3y FROM fund_returns WHERE amfi_code = '119551'"
        ).fetchone()
        assert row is not None
        # returns_1y: closest NAV within +/-30 days of (last - 1y) = 2025-04-08
        # No NAV within that window so should be NULL.
        assert row[0] is None
        assert row[1] == pytest.approx(10.0, abs=0.5)
