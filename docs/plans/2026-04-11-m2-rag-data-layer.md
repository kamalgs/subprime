# M2: RAG Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace live-only fund discovery with a DuckDB-backed RAG: download the InertExpert2911/Mutual_Fund_Data GitHub dataset, compute returns, curate a top-N fund universe per category, and inject it into the advisor's system prompt. mfdata.in is kept exclusively for real-time lookups.

**Architecture:** New `store.py`, `ingest.py`, `universe.py` modules in `subprime/data/`. DuckDB file at `~/.subprime/data/subprime.duckdb`. Advisor gets an optional `universe_context` parameter. New `subprime data refresh/stats` CLI commands.

**Tech Stack:** DuckDB 1.2+, httpx (for download), existing Typer/Rich/PydanticAI.

**Spec:** `docs/superpowers/specs/2026-04-11-m2-rag-data-layer-design.md`

---

### Task 1: Add DuckDB dependency, config paths, package layout

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/subprime/core/config.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add duckdb to pyproject.toml**

Edit `pyproject.toml`, add `"duckdb>=1.2"` to the `dependencies` list (after `httpx>=0.27`):

```toml
dependencies = [
    "pydantic>=2.0",
    "pydantic-ai>=0.1.0",
    "pydantic-settings>=2.0",
    "anthropic>=0.40",
    "httpx>=0.27",
    "duckdb>=1.2",
    "rich>=13.0",
    "typer>=0.12",
    "scipy>=1.14",
    "numpy>=2.0",
    "python-dotenv>=1.0",
    "gradio>=5.0",
]
```

- [ ] **Step 2: Run uv sync**

```bash
uv sync
```

Expected: DuckDB installs successfully.

- [ ] **Step 3: Add data paths to `src/subprime/core/config.py`**

Add these constants near the `DEFAULT_MODEL` constant (before the `Settings` class):

```python
from pathlib import Path

DEFAULT_MODEL = "anthropic:claude-haiku-4-5"

DATA_DIR = Path.home() / ".subprime" / "data"
DB_PATH = DATA_DIR / "subprime.duckdb"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/InertExpert2911/Mutual_Fund_Data/main"
GITHUB_LFS_BASE = "https://media.githubusercontent.com/media/InertExpert2911/Mutual_Fund_Data/main"
SCHEMES_CSV_URL = f"{GITHUB_RAW_BASE}/mutual_fund_data.csv"
NAV_PARQUET_URL = f"{GITHUB_LFS_BASE}/mutual_fund_nav_history.parquet"
CURATED_TOP_N = 15
```

Make sure `from pathlib import Path` is present at the top.

- [ ] **Step 4: Add `.subprime/` to .gitignore**

Edit `.gitignore`, add these lines:

```
.subprime/
*.duckdb
```

- [ ] **Step 5: Verify import works**

```bash
uv run python -c "from subprime.core.config import DATA_DIR, DB_PATH, SCHEMES_CSV_URL, NAV_PARQUET_URL, CURATED_TOP_N; print(DB_PATH)"
```

Expected: Prints `/home/agent/.subprime/data/subprime.duckdb` (or similar).

- [ ] **Step 6: Verify tests still pass**

```bash
uv run pytest -q
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/subprime/core/config.py .gitignore
git commit -m "chore(m2): add duckdb dep, data paths, gitignore"
```

---

### Task 2: DuckDB store module — connection and schema

**Files:**
- Create: `src/subprime/data/store.py`
- Create: `tests/test_data/test_store.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_data/test_store.py`:

```python
"""Tests for DuckDB store module."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from subprime.data.store import (
    ensure_schema,
    get_connection,
    get_refresh_stats,
    log_refresh,
)


@pytest.fixture
def memory_conn():
    conn = duckdb.connect(":memory:")
    ensure_schema(conn)
    yield conn
    conn.close()


class TestSchema:
    def test_tables_exist_after_ensure_schema(self, memory_conn):
        tables = {row[0] for row in memory_conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()}
        assert "schemes" in tables
        assert "nav_history" in tables
        assert "fund_returns" in tables
        assert "fund_universe" in tables
        assert "refresh_log" in tables

    def test_ensure_schema_idempotent(self, memory_conn):
        """Calling ensure_schema twice should not error."""
        ensure_schema(memory_conn)
        ensure_schema(memory_conn)
        # Still all tables present
        tables = {row[0] for row in memory_conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()}
        assert "schemes" in tables


class TestRefreshLog:
    def test_log_and_read_refresh(self, memory_conn):
        log_refresh(memory_conn, scheme_count=100, nav_count=5000)
        stats = get_refresh_stats(memory_conn)
        assert stats is not None
        assert stats["scheme_count"] == 100
        assert stats["nav_count"] == 5000
        assert stats["refreshed_at"] is not None

    def test_get_stats_empty(self, memory_conn):
        stats = get_refresh_stats(memory_conn)
        assert stats is None

    def test_multiple_refreshes_returns_latest(self, memory_conn):
        log_refresh(memory_conn, scheme_count=100, nav_count=5000)
        log_refresh(memory_conn, scheme_count=200, nav_count=10000)
        stats = get_refresh_stats(memory_conn)
        assert stats["scheme_count"] == 200


class TestGetConnection:
    def test_creates_parent_directory(self, tmp_path):
        db_path = tmp_path / "nested" / "dir" / "test.duckdb"
        conn = get_connection(db_path)
        assert db_path.parent.exists()
        assert db_path.exists()
        conn.close()

    def test_returns_duckdb_connection(self, tmp_path):
        conn = get_connection(tmp_path / "test.duckdb")
        assert isinstance(conn, duckdb.DuckDBPyConnection)
        conn.close()
```

- [ ] **Step 2: Run test to see it fail**

```bash
uv run pytest tests/test_data/test_store.py -v
```

Expected: FAIL — `subprime.data.store` module not found.

- [ ] **Step 3: Create the store module**

Create `src/subprime/data/store.py`:

```python
"""DuckDB store for mutual fund data.

Single responsibility: connection management + schema definition.
No business logic — that lives in ingest.py and universe.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb

from subprime.core.config import DB_PATH


def get_connection(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open (or create) a DuckDB connection at the given path.

    Creates parent directories if they don't exist.
    """
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all tables if they don't exist. Idempotent."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schemes (
            amfi_code VARCHAR PRIMARY KEY,
            name VARCHAR,
            amc VARCHAR,
            scheme_type VARCHAR,
            scheme_category VARCHAR,
            nav DOUBLE,
            latest_nav_date DATE,
            average_aum_cr DOUBLE,
            launch_date DATE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nav_history (
            amfi_code VARCHAR,
            nav_date DATE,
            nav DOUBLE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fund_returns (
            amfi_code VARCHAR PRIMARY KEY,
            returns_1y DOUBLE,
            returns_3y DOUBLE,
            returns_5y DOUBLE,
            last_computed_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fund_universe (
            amfi_code VARCHAR PRIMARY KEY,
            name VARCHAR,
            amc VARCHAR,
            category VARCHAR,
            sub_category VARCHAR,
            aum_cr DOUBLE,
            returns_1y DOUBLE,
            returns_3y DOUBLE,
            returns_5y DOUBLE,
            rank_in_category INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS refresh_log (
            refreshed_at TIMESTAMP,
            scheme_count INTEGER,
            nav_count INTEGER
        )
        """
    )


def log_refresh(
    conn: duckdb.DuckDBPyConnection,
    scheme_count: int,
    nav_count: int,
) -> None:
    """Record a successful data refresh."""
    conn.execute(
        "INSERT INTO refresh_log VALUES (?, ?, ?)",
        [datetime.now(timezone.utc), scheme_count, nav_count],
    )


def get_refresh_stats(conn: duckdb.DuckDBPyConnection) -> Optional[dict]:
    """Return the latest refresh row, or None if no refreshes recorded."""
    row = conn.execute(
        "SELECT refreshed_at, scheme_count, nav_count FROM refresh_log "
        "ORDER BY refreshed_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return {
        "refreshed_at": row[0],
        "scheme_count": row[1],
        "nav_count": row[2],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_data/test_store.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -q
```

Expected: All tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/subprime/data/store.py tests/test_data/test_store.py
git commit -m "feat(data): add DuckDB store with schema and refresh log"
```

---

### Task 3: Ingest module — load schemes and NAV history

**Files:**
- Create: `src/subprime/data/ingest.py`
- Create: `tests/test_data/test_ingest.py`
- Create: `tests/fixtures/sample_schemes.csv` (fixture file)
- Create: `tests/fixtures/sample_nav.parquet` (generated in test)

- [ ] **Step 1: Create fixtures directory and sample CSV**

```bash
mkdir -p tests/fixtures
```

Create `tests/fixtures/sample_schemes.csv`:

```csv
Scheme_Code,Scheme_Name,AMC,Scheme_Type,Scheme_Category,Scheme_NAV_Name,Scheme_Min_Amt,NAV,Latest_NAV_Date,Average_AUM_Cr,AAUM_Quarter,ISIN_Div_Payout/Growth,ISIN_Div_Reinvestment,ISIN_Div_Payout/Growth/Div_Reinvestment,Launch_Date,Closure_Date
119551,UTI Nifty 50 Index Fund - Direct Plan - Growth,UTI Mutual Fund,Open Ended,Equity Scheme - Index Fund,UTI Nifty 50 Index Fund - Direct Plan - Growth,5000,150.25,2026-04-08,12000.50,January - March 2026,INF789F1234,-,INF789F1234,2013-03-14,2013-03-14
120586,ICICI Pru Bluechip Fund - Direct Plan - Growth,ICICI Prudential Mutual Fund,Open Ended,Equity Scheme - Large Cap Fund,ICICI Pru Bluechip Fund - Direct Plan - Growth,5000,95.40,2026-04-08,48000.00,January - March 2026,INF109K1234,-,INF109K1234,2008-05-23,2008-05-23
122639,Parag Parikh Flexi Cap Fund - Direct Plan - Growth,PPFAS Mutual Fund,Open Ended,Equity Scheme - Flexi Cap Fund,Parag Parikh Flexi Cap Fund - Direct Plan - Growth,1000,88.05,2026-04-08,75000.00,January - March 2026,INF879O01027,-,INF879O01027,2013-05-24,2013-05-24
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_data/test_ingest.py`:

```python
"""Tests for ingest module — data loading pipeline."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from subprime.data.ingest import (
    compute_returns,
    load_nav_history,
    load_schemes,
)
from subprime.data.store import ensure_schema


FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def conn():
    c = duckdb.connect(":memory:")
    ensure_schema(c)
    yield c
    c.close()


class TestLoadSchemes:
    def test_loads_fixture_csv(self, conn):
        count = load_schemes(conn, FIXTURES / "sample_schemes.csv")
        assert count == 3
        rows = conn.execute("SELECT amfi_code, name, amc, scheme_category FROM schemes ORDER BY amfi_code").fetchall()
        assert rows[0][0] == "119551"
        assert "UTI Nifty 50" in rows[0][1]
        assert rows[0][2] == "UTI Mutual Fund"
        assert "Index Fund" in rows[0][3]

    def test_load_schemes_is_idempotent(self, conn):
        load_schemes(conn, FIXTURES / "sample_schemes.csv")
        load_schemes(conn, FIXTURES / "sample_schemes.csv")
        count = conn.execute("SELECT COUNT(*) FROM schemes").fetchone()[0]
        assert count == 3  # not duplicated


class TestLoadNavHistory:
    def test_loads_fixture_parquet(self, conn, tmp_path):
        # Write a tiny parquet file via DuckDB itself
        parquet_path = tmp_path / "sample_nav.parquet"
        conn.execute(
            f"COPY (SELECT * FROM (VALUES "
            f"('119551', DATE '2026-04-01', 148.5), "
            f"('119551', DATE '2026-04-02', 149.0), "
            f"('119551', DATE '2026-04-03', 150.25) "
            f") AS t(Scheme_Code, Date, NAV)) "
            f"TO '{parquet_path}' (FORMAT PARQUET)"
        )

        count = load_nav_history(conn, parquet_path)
        assert count == 3
        rows = conn.execute("SELECT amfi_code, nav_date, nav FROM nav_history ORDER BY nav_date").fetchall()
        assert rows[0][0] == "119551"
        assert rows[2][2] == 150.25


class TestComputeReturns:
    def test_known_cagr(self, conn):
        """Insert a synthetic NAV series with known CAGR and verify."""
        # NAV went from 100 → 112 over 1 year → 12% CAGR
        today = date.today()
        one_year_ago = today - timedelta(days=365)
        conn.execute(
            "INSERT INTO nav_history VALUES (?, ?, ?), (?, ?, ?)",
            ["TEST1", one_year_ago, 100.0, "TEST1", today, 112.0],
        )
        compute_returns(conn)
        row = conn.execute(
            "SELECT returns_1y, returns_3y, returns_5y FROM fund_returns WHERE amfi_code='TEST1'"
        ).fetchone()
        assert row is not None
        # 1y return should be ~12% (tolerance 0.5%)
        assert 11.5 < row[0] < 12.5
        assert row[1] is None  # insufficient history for 3y
        assert row[2] is None  # insufficient history for 5y

    def test_insufficient_history_nulls(self, conn):
        """Fund with <1y history should get NULL returns, no crash."""
        today = date.today()
        two_weeks_ago = today - timedelta(days=14)
        conn.execute(
            "INSERT INTO nav_history VALUES (?, ?, ?), (?, ?, ?)",
            ["SHORT1", two_weeks_ago, 100.0, "SHORT1", today, 101.0],
        )
        compute_returns(conn)
        # Either no row, or row with all NULLs — both are acceptable.
        row = conn.execute(
            "SELECT returns_1y, returns_3y, returns_5y FROM fund_returns WHERE amfi_code='SHORT1'"
        ).fetchone()
        if row is not None:
            assert row[0] is None

    def test_compute_returns_idempotent(self, conn):
        """Re-running should replace, not duplicate."""
        today = date.today()
        one_year_ago = today - timedelta(days=365)
        conn.execute(
            "INSERT INTO nav_history VALUES (?, ?, ?), (?, ?, ?)",
            ["TEST2", one_year_ago, 100.0, "TEST2", today, 110.0],
        )
        compute_returns(conn)
        compute_returns(conn)
        count = conn.execute(
            "SELECT COUNT(*) FROM fund_returns WHERE amfi_code='TEST2'"
        ).fetchone()[0]
        assert count == 1
```

- [ ] **Step 3: Run tests to see them fail**

```bash
uv run pytest tests/test_data/test_ingest.py -v
```

Expected: FAIL — ingest module not found.

- [ ] **Step 4: Create the ingest module**

Create `src/subprime/data/ingest.py`:

```python
"""Data ingestion pipeline: download GitHub dataset, load into DuckDB, compute returns."""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import httpx

from subprime.core.config import NAV_PARQUET_URL, SCHEMES_CSV_URL
from subprime.data.store import log_refresh

logger = logging.getLogger(__name__)


def load_schemes(conn: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """Load scheme details from CSV into the schemes table.

    Replaces existing rows (idempotent).

    Args:
        conn: DuckDB connection.
        csv_path: Path to the mutual_fund_data.csv file.

    Returns:
        Number of rows loaded.
    """
    conn.execute("DELETE FROM schemes")
    # Read the CSV with DuckDB's native auto-detection, project/rename columns.
    conn.execute(
        f"""
        INSERT INTO schemes (amfi_code, name, amc, scheme_type, scheme_category, nav, latest_nav_date, average_aum_cr, launch_date)
        SELECT
            CAST("Scheme_Code" AS VARCHAR) AS amfi_code,
            "Scheme_Name" AS name,
            "AMC" AS amc,
            "Scheme_Type" AS scheme_type,
            "Scheme_Category" AS scheme_category,
            TRY_CAST("NAV" AS DOUBLE) AS nav,
            TRY_CAST("Latest_NAV_Date" AS DATE) AS latest_nav_date,
            TRY_CAST("Average_AUM_Cr" AS DOUBLE) AS average_aum_cr,
            TRY_CAST("Launch_Date" AS DATE) AS launch_date
        FROM read_csv_auto('{csv_path}', header=True, all_varchar=False)
        """
    )
    return conn.execute("SELECT COUNT(*) FROM schemes").fetchone()[0]


def load_nav_history(conn: duckdb.DuckDBPyConnection, parquet_path: Path) -> int:
    """Load NAV history from parquet into the nav_history table.

    Replaces existing rows.

    Args:
        conn: DuckDB connection.
        parquet_path: Path to the mutual_fund_nav_history.parquet file.

    Returns:
        Number of rows loaded.
    """
    conn.execute("DELETE FROM nav_history")
    conn.execute(
        f"""
        INSERT INTO nav_history (amfi_code, nav_date, nav)
        SELECT
            CAST("Scheme_Code" AS VARCHAR) AS amfi_code,
            CAST("Date" AS DATE) AS nav_date,
            CAST("NAV" AS DOUBLE) AS nav
        FROM read_parquet('{parquet_path}')
        """
    )
    return conn.execute("SELECT COUNT(*) FROM nav_history").fetchone()[0]


def compute_returns(conn: duckdb.DuckDBPyConnection) -> int:
    """Compute 1y/3y/5y CAGR for all schemes in nav_history.

    Uses the earliest NAV within each window and the latest NAV for CAGR.
    Schemes with insufficient history get NULL for that window.

    Returns:
        Number of schemes with at least one non-null return.
    """
    conn.execute("DELETE FROM fund_returns")
    conn.execute(
        """
        INSERT INTO fund_returns (amfi_code, returns_1y, returns_3y, returns_5y, last_computed_at)
        WITH latest AS (
            SELECT amfi_code, MAX(nav_date) AS last_date
            FROM nav_history
            GROUP BY amfi_code
        ),
        latest_nav AS (
            SELECT h.amfi_code, h.nav_date AS last_date, h.nav AS last_nav
            FROM nav_history h
            JOIN latest l ON h.amfi_code = l.amfi_code AND h.nav_date = l.last_date
        ),
        windows AS (
            SELECT
                ln.amfi_code,
                ln.last_date,
                ln.last_nav,
                -- earliest NAV on or after (last_date - 365 days), for 1y window
                (SELECT nav FROM nav_history h
                 WHERE h.amfi_code = ln.amfi_code
                   AND h.nav_date <= ln.last_date - INTERVAL '365 days' + INTERVAL '30 days'
                   AND h.nav_date >= ln.last_date - INTERVAL '365 days' - INTERVAL '30 days'
                 ORDER BY ABS(date_diff('day', h.nav_date, ln.last_date - INTERVAL '365 days')) ASC
                 LIMIT 1) AS nav_1y,
                (SELECT nav FROM nav_history h
                 WHERE h.amfi_code = ln.amfi_code
                   AND h.nav_date <= ln.last_date - INTERVAL '3 years' + INTERVAL '60 days'
                   AND h.nav_date >= ln.last_date - INTERVAL '3 years' - INTERVAL '60 days'
                 ORDER BY ABS(date_diff('day', h.nav_date, ln.last_date - INTERVAL '3 years')) ASC
                 LIMIT 1) AS nav_3y,
                (SELECT nav FROM nav_history h
                 WHERE h.amfi_code = ln.amfi_code
                   AND h.nav_date <= ln.last_date - INTERVAL '5 years' + INTERVAL '90 days'
                   AND h.nav_date >= ln.last_date - INTERVAL '5 years' - INTERVAL '90 days'
                 ORDER BY ABS(date_diff('day', h.nav_date, ln.last_date - INTERVAL '5 years')) ASC
                 LIMIT 1) AS nav_5y
            FROM latest_nav ln
        )
        SELECT
            amfi_code,
            CASE WHEN nav_1y IS NULL OR nav_1y <= 0 THEN NULL
                 ELSE ((last_nav / nav_1y) - 1) * 100 END AS returns_1y,
            CASE WHEN nav_3y IS NULL OR nav_3y <= 0 THEN NULL
                 ELSE (POWER(last_nav / nav_3y, 1.0/3) - 1) * 100 END AS returns_3y,
            CASE WHEN nav_5y IS NULL OR nav_5y <= 0 THEN NULL
                 ELSE (POWER(last_nav / nav_5y, 1.0/5) - 1) * 100 END AS returns_5y,
            CURRENT_TIMESTAMP AS last_computed_at
        FROM windows
        WHERE nav_1y IS NOT NULL OR nav_3y IS NOT NULL OR nav_5y IS NOT NULL
        """
    )
    return conn.execute("SELECT COUNT(*) FROM fund_returns").fetchone()[0]


async def download_dataset(target_dir: Path) -> tuple[Path, Path]:
    """Download the GitHub dataset files to the target directory.

    Returns:
        (csv_path, parquet_path) for the downloaded files.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    csv_path = target_dir / "mutual_fund_data.csv"
    parquet_path = target_dir / "mutual_fund_nav_history.parquet"

    async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
        logger.info("Downloading %s", SCHEMES_CSV_URL)
        resp = await client.get(SCHEMES_CSV_URL)
        resp.raise_for_status()
        csv_path.write_bytes(resp.content)

        logger.info("Downloading %s", NAV_PARQUET_URL)
        resp = await client.get(NAV_PARQUET_URL)
        resp.raise_for_status()
        parquet_path.write_bytes(resp.content)

    return csv_path, parquet_path


async def refresh(conn: duckdb.DuckDBPyConnection, data_dir: Path) -> dict:
    """Full refresh: download → load schemes → load NAV → compute returns.

    Returns:
        Dict with scheme_count, nav_count, returns_count.
    """
    csv_path, parquet_path = await download_dataset(data_dir)
    scheme_count = load_schemes(conn, csv_path)
    nav_count = load_nav_history(conn, parquet_path)
    returns_count = compute_returns(conn)
    log_refresh(conn, scheme_count=scheme_count, nav_count=nav_count)
    return {
        "scheme_count": scheme_count,
        "nav_count": nav_count,
        "returns_count": returns_count,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_data/test_ingest.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest -q
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/subprime/data/ingest.py tests/test_data/test_ingest.py tests/fixtures/sample_schemes.csv
git commit -m "feat(data): add ingest pipeline for schemes, NAV, and returns"
```

---

### Task 4: Universe module — curation and RAG context rendering

**Files:**
- Create: `src/subprime/data/universe.py`
- Create: `tests/test_data/test_universe.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_data/test_universe.py`:

```python
"""Tests for fund universe curation and RAG context rendering."""
from __future__ import annotations

import duckdb
import pytest

from subprime.data.store import ensure_schema
from subprime.data.universe import (
    CURATED_CATEGORIES,
    build_universe,
    normalize_category,
    render_universe_context,
    search_universe,
)


@pytest.fixture
def conn():
    c = duckdb.connect(":memory:")
    ensure_schema(c)
    yield c
    c.close()


def _populate(conn, schemes):
    """Helper: insert schemes (amfi_code, name, amc, category, aum, returns_1y, returns_3y, returns_5y)."""
    for s in schemes:
        conn.execute(
            "INSERT INTO schemes (amfi_code, name, amc, scheme_category, average_aum_cr) "
            "VALUES (?, ?, ?, ?, ?)",
            [s[0], s[1], s[2], s[3], s[4]],
        )
        conn.execute(
            "INSERT INTO fund_returns (amfi_code, returns_1y, returns_3y, returns_5y, last_computed_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [s[0], s[5], s[6], s[7]],
        )


class TestNormalizeCategory:
    def test_large_cap(self):
        assert normalize_category("Equity Scheme - Large Cap Fund") == "Large Cap"

    def test_mid_cap(self):
        assert normalize_category("Equity Scheme - Mid Cap Fund") == "Mid Cap"

    def test_index(self):
        assert normalize_category("Equity Scheme - Index Fund") == "Index"

    def test_elss(self):
        assert normalize_category("Equity Scheme - ELSS") == "ELSS"

    def test_flexi_cap(self):
        assert normalize_category("Equity Scheme - Flexi Cap Fund") == "Flexi Cap"

    def test_unmatched_returns_none(self):
        assert normalize_category("Something else entirely") is None


class TestBuildUniverse:
    def test_top_n_per_category(self, conn):
        # 3 Large Cap funds — ranked by 5y returns
        _populate(conn, [
            ("100", "Fund A", "AMC 1", "Equity Scheme - Large Cap Fund", 10000.0, 12.0, 15.0, 14.0),
            ("200", "Fund B", "AMC 2", "Equity Scheme - Large Cap Fund", 8000.0, 11.0, 14.0, 13.5),
            ("300", "Fund C", "AMC 3", "Equity Scheme - Large Cap Fund", 5000.0, 10.0, 13.0, 12.0),
        ])
        count = build_universe(conn, top_n_per_category=2)
        assert count == 2
        rows = conn.execute(
            "SELECT amfi_code, rank_in_category FROM fund_universe ORDER BY rank_in_category"
        ).fetchall()
        assert rows[0][0] == "100"  # best
        assert rows[1][0] == "200"

    def test_multiple_categories(self, conn):
        _populate(conn, [
            ("100", "Large A", "AMC 1", "Equity Scheme - Large Cap Fund", 10000.0, 12.0, 15.0, 14.0),
            ("200", "Mid A", "AMC 2", "Equity Scheme - Mid Cap Fund", 8000.0, 16.0, 18.0, 17.0),
            ("300", "Index A", "AMC 3", "Equity Scheme - Index Fund", 5000.0, 11.0, 13.0, 12.5),
        ])
        build_universe(conn, top_n_per_category=5)
        cats = {row[0] for row in conn.execute(
            "SELECT DISTINCT category FROM fund_universe"
        ).fetchall()}
        assert "Large Cap" in cats
        assert "Mid Cap" in cats
        assert "Index" in cats

    def test_excludes_uncategorized(self, conn):
        _populate(conn, [
            ("999", "Mystery", "AMC", "Unknown Category", 1000.0, 10.0, 10.0, 10.0),
        ])
        build_universe(conn, top_n_per_category=5)
        assert conn.execute("SELECT COUNT(*) FROM fund_universe").fetchone()[0] == 0

    def test_rebuild_replaces(self, conn):
        _populate(conn, [
            ("100", "Fund A", "AMC 1", "Equity Scheme - Large Cap Fund", 10000.0, 12.0, 15.0, 14.0),
        ])
        build_universe(conn, top_n_per_category=5)
        build_universe(conn, top_n_per_category=5)
        assert conn.execute("SELECT COUNT(*) FROM fund_universe").fetchone()[0] == 1


class TestRenderUniverseContext:
    def test_includes_category_headers(self, conn):
        _populate(conn, [
            ("100", "Fund A", "AMC 1", "Equity Scheme - Large Cap Fund", 10000.0, 12.0, 15.0, 14.0),
            ("200", "Fund B", "AMC 2", "Equity Scheme - Mid Cap Fund", 8000.0, 16.0, 18.0, 17.0),
        ])
        build_universe(conn, top_n_per_category=5)
        text = render_universe_context(conn)
        assert "Large Cap" in text
        assert "Mid Cap" in text
        assert "Fund A" in text
        assert "Fund B" in text
        # Should show returns
        assert "15" in text or "14" in text

    def test_empty_universe_returns_placeholder(self, conn):
        text = render_universe_context(conn)
        assert "No curated fund universe" in text or text.strip() != ""


class TestSearchUniverse:
    def test_filter_by_category(self, conn):
        _populate(conn, [
            ("100", "Large A", "AMC 1", "Equity Scheme - Large Cap Fund", 10000.0, 12.0, 15.0, 14.0),
            ("200", "Mid A", "AMC 2", "Equity Scheme - Mid Cap Fund", 8000.0, 16.0, 18.0, 17.0),
        ])
        build_universe(conn, top_n_per_category=5)

        results = search_universe(conn, category="Large Cap")
        assert len(results) == 1
        assert results[0].name == "Large A"

    def test_no_filter_returns_all(self, conn):
        _populate(conn, [
            ("100", "Large A", "AMC 1", "Equity Scheme - Large Cap Fund", 10000.0, 12.0, 15.0, 14.0),
            ("200", "Mid A", "AMC 2", "Equity Scheme - Mid Cap Fund", 8000.0, 16.0, 18.0, 17.0),
        ])
        build_universe(conn, top_n_per_category=5)
        results = search_universe(conn)
        assert len(results) == 2

    def test_empty_returns_empty_list(self, conn):
        results = search_universe(conn, category="Large Cap")
        assert results == []


class TestCuratedCategoriesConstant:
    def test_expected_categories(self):
        assert "Large Cap" in CURATED_CATEGORIES
        assert "Mid Cap" in CURATED_CATEGORIES
        assert "Index" in CURATED_CATEGORIES
        assert "ELSS" in CURATED_CATEGORIES
```

- [ ] **Step 2: Run tests to see them fail**

```bash
uv run pytest tests/test_data/test_universe.py -v
```

Expected: FAIL — universe module not found.

- [ ] **Step 3: Create the universe module**

Create `src/subprime/data/universe.py`:

```python
"""Fund universe curation and RAG context rendering.

Takes raw scheme data, computes a curated top-N per category, and renders
it as compact markdown text for injection into the advisor's system prompt.
"""
from __future__ import annotations

from typing import Optional

import duckdb

from subprime.core.config import CURATED_TOP_N
from subprime.core.models import MutualFund


# Canonical display categories, in the order they should appear in the context.
CURATED_CATEGORIES: list[str] = [
    "Large Cap",
    "Large & Mid Cap",
    "Mid Cap",
    "Small Cap",
    "Flexi Cap",
    "Multi Cap",
    "ELSS",
    "Index",
    "Hybrid",
    "Debt",
    "Gold",
]

# Mapping from substrings in raw scheme_category to canonical names.
# Order matters — first match wins.
_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    ("Large & Mid Cap", "Large & Mid Cap"),
    ("Large Cap", "Large Cap"),
    ("Mid Cap", "Mid Cap"),
    ("Small Cap", "Small Cap"),
    ("Flexi Cap", "Flexi Cap"),
    ("Multi Cap", "Multi Cap"),
    ("ELSS", "ELSS"),
    ("Index Fund", "Index"),
    ("Hybrid", "Hybrid"),
    ("Aggressive Hybrid", "Hybrid"),
    ("Conservative Hybrid", "Hybrid"),
    ("Balanced", "Hybrid"),
    ("Debt Scheme", "Debt"),
    ("Gilt", "Debt"),
    ("Liquid Fund", "Debt"),
    ("Short Duration", "Debt"),
    ("Corporate Bond", "Debt"),
    ("Gold", "Gold"),
]


def normalize_category(raw: Optional[str]) -> Optional[str]:
    """Map a raw scheme_category string to a canonical display category."""
    if not raw:
        return None
    for needle, canonical in _CATEGORY_PATTERNS:
        if needle.lower() in raw.lower():
            return canonical
    return None


def build_universe(
    conn: duckdb.DuckDBPyConnection,
    top_n_per_category: int = CURATED_TOP_N,
) -> int:
    """Curate top-N funds per canonical category and populate fund_universe.

    Ranking criterion: 5y CAGR (NULLS LAST), then 3y, then AUM, then 1y.
    Prefers larger, longer-track-record funds.

    Returns:
        Total number of funds in the universe.
    """
    # Build the CASE mapping from raw categories to canonical ones (one CASE per canonical)
    case_expr = "CASE "
    for needle, canonical in _CATEGORY_PATTERNS:
        needle_sql = needle.replace("'", "''")
        canonical_sql = canonical.replace("'", "''")
        case_expr += f"WHEN s.scheme_category ILIKE '%{needle_sql}%' THEN '{canonical_sql}' "
    case_expr += "ELSE NULL END"

    conn.execute("DELETE FROM fund_universe")
    conn.execute(
        f"""
        INSERT INTO fund_universe (
            amfi_code, name, amc, category, sub_category,
            aum_cr, returns_1y, returns_3y, returns_5y, rank_in_category
        )
        WITH categorized AS (
            SELECT
                s.amfi_code,
                s.name,
                s.amc,
                {case_expr} AS category,
                s.scheme_category AS sub_category,
                s.average_aum_cr AS aum_cr,
                r.returns_1y,
                r.returns_3y,
                r.returns_5y
            FROM schemes s
            LEFT JOIN fund_returns r ON s.amfi_code = r.amfi_code
            WHERE s.name NOT ILIKE '%IDCW%'
              AND s.name NOT ILIKE '%dividend%'
        ),
        ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY category
                    ORDER BY
                        returns_5y DESC NULLS LAST,
                        returns_3y DESC NULLS LAST,
                        aum_cr DESC NULLS LAST,
                        returns_1y DESC NULLS LAST
                ) AS rank_in_category
            FROM categorized
            WHERE category IS NOT NULL
        )
        SELECT
            amfi_code, name, amc, category, sub_category,
            aum_cr, returns_1y, returns_3y, returns_5y, rank_in_category
        FROM ranked
        WHERE rank_in_category <= {top_n_per_category}
        """
    )
    return conn.execute("SELECT COUNT(*) FROM fund_universe").fetchone()[0]


def render_universe_context(conn: duckdb.DuckDBPyConnection) -> str:
    """Render the curated fund universe as compact markdown for LLM context."""
    count = conn.execute("SELECT COUNT(*) FROM fund_universe").fetchone()[0]
    if count == 0:
        return "No curated fund universe available. Use live search tools if needed."

    parts: list[str] = ["## Curated Fund Universe (India)\n"]
    parts.append(
        "Use these funds as the primary source when building plans. "
        "All returns are CAGR % computed from historical NAV.\n"
    )

    for category in CURATED_CATEGORIES:
        rows = conn.execute(
            """
            SELECT amfi_code, name, amc, aum_cr, returns_1y, returns_3y, returns_5y
            FROM fund_universe
            WHERE category = ?
            ORDER BY rank_in_category
            """,
            [category],
        ).fetchall()
        if not rows:
            continue
        parts.append(f"\n### {category}")
        parts.append("| Fund | AMC | AMFI | 1y | 3y | 5y | AUM (Cr) |")
        parts.append("|---|---|---|---|---|---|---|")
        for amfi, name, amc, aum, r1, r3, r5 in rows:
            def f(v: Optional[float]) -> str:
                return f"{v:.1f}%" if v is not None else "-"
            def fa(v: Optional[float]) -> str:
                return f"{v:,.0f}" if v is not None else "-"
            parts.append(f"| {name} | {amc} | {amfi} | {f(r1)} | {f(r3)} | {f(r5)} | {fa(aum)} |")

    return "\n".join(parts) + "\n"


def search_universe(
    conn: duckdb.DuckDBPyConnection,
    category: Optional[str] = None,
    limit: int = 20,
) -> list[MutualFund]:
    """Query the curated universe as MutualFund objects.

    Args:
        conn: DuckDB connection.
        category: Filter to a canonical category (e.g. "Large Cap"). None = all.
        limit: Max results.

    Returns:
        List of MutualFund objects.
    """
    if category:
        rows = conn.execute(
            """
            SELECT amfi_code, name, amc, category, sub_category,
                   aum_cr, returns_1y, returns_3y, returns_5y
            FROM fund_universe
            WHERE category = ?
            ORDER BY rank_in_category
            LIMIT ?
            """,
            [category, limit],
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT amfi_code, name, amc, category, sub_category,
                   aum_cr, returns_1y, returns_3y, returns_5y
            FROM fund_universe
            ORDER BY category, rank_in_category
            LIMIT ?
            """,
            [limit],
        ).fetchall()

    return [
        MutualFund(
            amfi_code=r[0],
            name=r[1],
            category=r[3] or "",
            sub_category=r[4] or "",
            fund_house=r[2] or "",
            nav=0.0,  # not in universe — fetch via get_fund_performance if needed
            expense_ratio=0.0,
            aum_cr=r[5],
            returns_1y=r[6],
            returns_3y=r[7],
            returns_5y=r[8],
        )
        for r in rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_data/test_universe.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/subprime/data/universe.py tests/test_data/test_universe.py
git commit -m "feat(data): add fund universe curation and RAG context renderer"
```

---

### Task 5: Update tools — search_funds_universe + keep live lookups

**Files:**
- Modify: `src/subprime/data/tools.py`
- Modify: `src/subprime/data/__init__.py`
- Modify: `tests/test_data/test_tools.py`

- [ ] **Step 1: Update the tools test**

Append to `tests/test_data/test_tools.py`:

```python
# ---------------------------------------------------------------------------
# search_funds_universe tool (DuckDB-backed, offline)
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
```

- [ ] **Step 2: Run to see it fail**

```bash
uv run pytest tests/test_data/test_tools.py::TestSearchFundsUniverseTool -v
```

Expected: FAIL — `search_funds_universe` doesn't exist.

- [ ] **Step 3: Update `src/subprime/data/tools.py`**

Replace the full contents of `src/subprime/data/tools.py`:

```python
"""PydanticAI tool functions for mutual fund data lookup.

Plain async functions registered on the advisor agent. Each docstring is
exposed to the LLM as the tool description.

- search_funds_universe: queries the curated DuckDB universe (offline, fast)
- get_fund_performance: hits mfdata.in for real-time NAV/details
- compare_funds: real-time multi-fund comparison via mfdata.in
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from subprime.core.config import DB_PATH
from subprime.core.models import MutualFund
from subprime.data.client import MFDataClient


def _db_path() -> Path:
    """Return the current DuckDB path. Indirection for test monkeypatching."""
    return DB_PATH


async def search_funds_universe(
    category: Optional[str] = None,
    limit: int = 20,
) -> list[MutualFund]:
    """Search the curated Indian mutual fund universe by category.

    The universe contains the top funds per category ranked by 5-year CAGR,
    including computed 1y/3y/5y returns and AUM. This is the primary way to
    discover funds when building a plan — it is fast, offline, and grounded
    in historical data.

    Args:
        category: One of "Large Cap", "Large & Mid Cap", "Mid Cap", "Small Cap",
                  "Flexi Cap", "Multi Cap", "ELSS", "Index", "Hybrid", "Debt", "Gold".
                  None returns funds from all categories.
        limit: Max number of funds to return (default 20).

    Returns:
        List of MutualFund objects with computed returns. NAV will be 0 —
        call get_fund_performance(amfi_code) for the current live NAV.
    """
    import duckdb

    from subprime.data.universe import search_universe

    path = _db_path()
    if not path.exists():
        return []
    conn = duckdb.connect(str(path), read_only=True)
    try:
        return search_universe(conn, category=category, limit=limit)
    finally:
        conn.close()


async def get_fund_performance(amfi_code: str) -> MutualFund:
    """Get live real-time data for a specific mutual fund by AMFI code.

    Use this to verify current NAV, expense ratio, and latest details before
    finalizing a fund recommendation. Hits the live mfdata.in API.

    Args:
        amfi_code: The AMFI registration number (e.g. "119551").

    Returns:
        A MutualFund with the latest available data from the API.

    Raises:
        httpx.HTTPStatusError: If the fund is not found.
    """
    async with MFDataClient() as client:
        details = await client.get_fund_details(amfi_code)
        return MFDataClient.details_to_mutual_fund(details)


async def compare_funds(amfi_codes: list[str]) -> list[MutualFund]:
    """Compare multiple mutual funds side by side using live data.

    Fetches detailed data for each fund via mfdata.in so you can compare
    NAV, expense ratios, AUM, and ratings across schemes.

    Args:
        amfi_codes: List of AMFI registration numbers to compare.

    Returns:
        List of MutualFund objects, one per code, in the same order.
    """
    if not amfi_codes:
        return []
    async with MFDataClient() as client:

        async def _fetch(code: str) -> MutualFund:
            details = await client.get_fund_details(code)
            return MFDataClient.details_to_mutual_fund(details)

        return list(await asyncio.gather(*[_fetch(c) for c in amfi_codes]))
```

- [ ] **Step 4: Update `src/subprime/data/__init__.py`**

Replace with:

```python
"""subprime.data — Mutual fund data client, DuckDB store, and PydanticAI tools."""

from subprime.data.client import MFDataClient
from subprime.data.schemas import SchemeDetails, SchemeSearchResult
from subprime.data.tools import compare_funds, get_fund_performance, search_funds_universe

__all__ = [
    "MFDataClient",
    "SchemeDetails",
    "SchemeSearchResult",
    "compare_funds",
    "get_fund_performance",
    "search_funds_universe",
]
```

- [ ] **Step 5: Run the tools tests**

```bash
uv run pytest tests/test_data/test_tools.py -v
```

Expected: Existing tests may fail because they import `search_funds` (old name). Check output.

- [ ] **Step 6: Remove obsolete `search_funds` tests**

Open `tests/test_data/test_tools.py` and delete the entire `TestSearchFundsTool` class (the existing one testing the old `search_funds` function — not the new `TestSearchFundsUniverseTool` we just added). The advisor no longer uses `search_funds`; it uses `search_funds_universe` instead.

Verify by running:

```bash
uv run pytest tests/test_data/test_tools.py -v
```

Expected: `TestSearchFundsUniverseTool::test_search_universe_by_category` and `TestSearchFundsUniverseTool::test_search_universe_no_db` PASS. Other tests (`TestGetFundPerformanceTool`, `TestCompareFundsTool`) still pass.

- [ ] **Step 7: Run full suite — expect failures in advisor tests**

```bash
uv run pytest -q 2>&1 | tail -30
```

Expected: Advisor and integration tests may fail because `create_advisor` still imports the old `search_funds`. We'll fix those in the next task.

- [ ] **Step 8: Commit**

```bash
git add src/subprime/data/tools.py src/subprime/data/__init__.py tests/test_data/test_tools.py
git commit -m "feat(data): replace search_funds with DuckDB-backed search_funds_universe"
```

---

### Task 6: Advisor integration — inject universe into system prompt

**Files:**
- Modify: `src/subprime/advisor/agent.py`
- Modify: `src/subprime/advisor/planner.py`
- Modify: `src/subprime/advisor/prompts/planning.md`
- Modify: `tests/test_advisor/test_planner.py`
- Modify: `tests/test_advisor/test_strategy.py`

- [ ] **Step 1: Update `src/subprime/advisor/agent.py`**

Replace the `create_advisor` function body (keep the signature but add a `universe_context` parameter). Also update the tools list to use `search_funds_universe`.

Replace the import line:
```python
from subprime.data.tools import compare_funds, get_fund_performance, search_funds
```
with:
```python
from subprime.data.tools import compare_funds, get_fund_performance, search_funds_universe
```

Replace the `create_advisor` function:

```python
def create_advisor(
    prompt_hooks: dict[str, str] | None = None,
    universe_context: str | None = None,
    model: str = DEFAULT_MODEL,
) -> Agent:
    """Create a financial advisor agent.

    Args:
        prompt_hooks: Optional dict of hook_name -> content to inject.
            e.g. {"philosophy": "Always prefer index funds."}
        universe_context: Optional markdown text describing the curated fund
            universe. When provided, it's appended to the system prompt so the
            agent knows which funds are available before making any tool calls.
        model: The LLM model identifier.

    Returns:
        A PydanticAI Agent configured with tools and prompts.
    """
    base = load_prompt("base")
    planning = load_prompt("planning")

    philosophy = ""
    if prompt_hooks and "philosophy" in prompt_hooks:
        philosophy = prompt_hooks["philosophy"]
    else:
        hook_path = _PROMPTS_DIR / "hooks" / "philosophy.md"
        if hook_path.exists():
            philosophy = hook_path.read_text().strip()

    parts = [base, planning]
    if philosophy:
        parts.append(f"## Investment Philosophy\n\n{philosophy}")
    if universe_context:
        parts.append(universe_context)

    system_prompt = "\n\n---\n\n".join(parts)

    return Agent(
        model,
        system_prompt=system_prompt,
        output_type=InvestmentPlan,
        tools=[search_funds_universe, get_fund_performance, compare_funds],
        retries=3,
        defer_model_check=True,
    )
```

- [ ] **Step 2: Update `src/subprime/advisor/prompts/planning.md`**

Replace the `## Fund selection rules` section (at the end of the file) with:

```markdown
## Fund selection rules

- Use `search_funds_universe` to discover candidate funds by category. The curated universe is your primary source — it contains top funds per category ranked by 5y CAGR.
- Use `get_fund_performance(amfi_code)` to fetch live NAV and details for a specific fund before finalizing a recommendation.
- Use `compare_funds(amfi_codes)` when comparing a shortlist side-by-side.
- **Diversify across fund houses** — no single AMC should hold more than 40% of the portfolio. Spread across at least 3 different fund houses.
- Prefer **direct plans** over regular plans (lower expense ratio)
- Prefer **growth option** over IDCW for long-term goals
- For each fund, prefer: higher 5y CAGR (from the universe), lower expense ratio (from live lookup), larger AUM for stability
- Include the fund's expense ratio and rating in the rationale for each allocation
```

- [ ] **Step 3: Update `src/subprime/advisor/planner.py`**

Replace the full contents:

```python
"""Plan generation — strategy outlines and detailed investment plans."""
from __future__ import annotations

import logging
from pathlib import Path

from subprime.advisor.agent import create_advisor, create_strategy_advisor
from subprime.core.config import DB_PATH, DEFAULT_MODEL
from subprime.core.models import InvestmentPlan, InvestorProfile, StrategyOutline

logger = logging.getLogger(__name__)


def _load_universe_context(db_path: Path = DB_PATH) -> str | None:
    """Load the curated fund universe as markdown text from DuckDB.

    Returns None if the database doesn't exist or is empty — the advisor
    will then work without the universe (falling back to live tool calls).
    """
    if not db_path.exists():
        return None
    try:
        import duckdb

        from subprime.data.universe import render_universe_context

        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            return render_universe_context(conn)
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to load fund universe from %s", db_path, exc_info=True)
        return None


async def generate_strategy(
    profile: InvestorProfile,
    feedback: str | None = None,
    current_strategy: StrategyOutline | None = None,
    prompt_hooks: dict[str, str] | None = None,
    model: str = DEFAULT_MODEL,
) -> StrategyOutline:
    """Generate or revise a high-level investment strategy."""
    agent = create_strategy_advisor(prompt_hooks=prompt_hooks, model=model)

    parts = [f"Investor profile:\n\n{profile.model_dump_json(indent=2)}"]

    if current_strategy and feedback:
        parts.append(
            f"\nCurrent strategy:\n\n{current_strategy.model_dump_json(indent=2)}"
            f"\n\nInvestor feedback: {feedback}"
            f"\n\nRevise the strategy based on this feedback."
        )
    elif current_strategy:
        parts.append(
            f"\nCurrent strategy:\n\n{current_strategy.model_dump_json(indent=2)}"
            f"\n\nRefine this strategy."
        )

    result = await agent.run("\n".join(parts))
    return result.output


async def generate_plan(
    profile: InvestorProfile,
    strategy: StrategyOutline | None = None,
    prompt_hooks: dict[str, str] | None = None,
    include_universe: bool = True,
    model: str = DEFAULT_MODEL,
) -> InvestmentPlan:
    """Generate a detailed investment plan.

    Args:
        profile: Complete investor profile.
        strategy: Optional approved strategy to guide fund selection.
        prompt_hooks: Optional philosophy injection for experiments.
        include_universe: If True (default), load the curated fund universe
            from DuckDB and inject into the agent's system prompt.
        model: LLM model identifier.
    """
    universe_ctx = _load_universe_context() if include_universe else None
    agent = create_advisor(
        prompt_hooks=prompt_hooks,
        universe_context=universe_ctx,
        model=model,
    )

    parts = [
        f"Create a detailed mutual fund investment plan for this investor:\n\n"
        f"{profile.model_dump_json(indent=2)}"
    ]

    if strategy:
        parts.append(
            f"\nThe investor has approved this strategy direction:\n\n"
            f"{strategy.model_dump_json(indent=2)}\n\n"
            f"Select specific mutual fund schemes that implement this strategy. "
            f"Prefer funds from the curated universe above when possible."
        )

    result = await agent.run("\n".join(parts))
    return result.output
```

- [ ] **Step 4: Update existing advisor tests that check tool names**

In `tests/test_advisor/test_planner.py`, find the test that checks `_function_toolset.tools` (likely `test_create_advisor_has_three_tools` or similar) and update it to look for `search_funds_universe` instead of `search_funds`:

Find:
```python
def test_create_advisor_has_three_tools():
    agent = create_advisor()
    tool_names = set(agent._function_toolset.tools.keys())
    assert "search_funds" in tool_names
```

Replace with:
```python
def test_create_advisor_has_three_tools():
    agent = create_advisor()
    tool_names = set(agent._function_toolset.tools.keys())
    assert "search_funds_universe" in tool_names
    assert "get_fund_performance" in tool_names
    assert "compare_funds" in tool_names
```

Also find any other place in test_planner.py or test_strategy.py that references the string `"search_funds"` and update it to `"search_funds_universe"`. Run `grep -r '"search_funds"' tests/test_advisor/` to find them.

- [ ] **Step 5: Add new tests for universe injection**

Append to `tests/test_advisor/test_planner.py`:

```python
def test_create_advisor_with_universe_context():
    """universe_context should be injected into the system prompt."""
    agent = create_advisor(universe_context="UNIVERSE_MARKER: foo bar baz")
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "UNIVERSE_MARKER" in combined


def test_create_advisor_without_universe_context():
    """No universe → no marker in prompt."""
    agent = create_advisor()
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "UNIVERSE_MARKER" not in combined


@pytest.mark.asyncio
async def test_generate_plan_include_universe_false_skips_db(sample_profile, tmp_path, monkeypatch):
    """include_universe=False should not try to read the DB."""
    from subprime.advisor.planner import generate_plan

    def _should_not_be_called(*args, **kwargs):
        raise AssertionError("_load_universe_context should not be called")

    monkeypatch.setattr("subprime.advisor.planner._load_universe_context", _should_not_be_called)

    fake_plan = _make_fake_plan()
    mock_result = MagicMock()
    mock_result.output = fake_plan

    with patch("subprime.advisor.planner.create_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        plan = await generate_plan(sample_profile, include_universe=False)

    assert isinstance(plan, InvestmentPlan)
    # create_advisor should have been called with universe_context=None
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs.get("universe_context") is None
```

- [ ] **Step 6: Run advisor tests**

```bash
uv run pytest tests/test_advisor/ -v
```

Expected: All tests pass, including the 3 new ones.

- [ ] **Step 7: Run full suite**

```bash
uv run pytest -q
```

Expected: Integration tests and functional tests may still reference `search_funds` — check output. If so, update them similarly (grep `search_funds` in tests/, replace with `search_funds_universe` where it refers to tool names).

- [ ] **Step 8: Fix any remaining test failures**

Run:
```bash
grep -rn '"search_funds"' tests/
grep -rn 'search_funds\b' tests/ | grep -v search_funds_universe
```

For each match that references the tool string, change `"search_funds"` to `"search_funds_universe"`. Re-run the full suite.

- [ ] **Step 9: Commit**

```bash
git add src/subprime/advisor/ tests/test_advisor/ tests/
git commit -m "feat(advisor): inject curated universe into system prompt, switch tools"
```

---

### Task 7: CLI — `subprime data refresh` and `subprime data stats`

**Files:**
- Modify: `src/subprime/cli.py`
- Modify: `tests/test_functional.py`

- [ ] **Step 1: Write the failing functional tests**

Append to `tests/test_functional.py` (at the bottom):

```python
# ===========================================================================
# CLI: subprime data
# ===========================================================================


class TestCLIData:
    def test_data_help(self):
        result = runner.invoke(app, ["data", "--help"])
        assert result.exit_code == 0
        assert "refresh" in result.output
        assert "stats" in result.output

    def test_data_stats_empty_db(self, tmp_path, monkeypatch):
        """No DB file → stats command should report no data, exit 0."""
        monkeypatch.setattr("subprime.cli.DB_PATH", tmp_path / "missing.duckdb")
        result = runner.invoke(app, ["data", "stats"])
        assert result.exit_code == 0
        assert "no" in result.output.lower() or "No" in result.output

    def test_data_stats_populated(self, tmp_path, monkeypatch):
        """Populated DB → stats command should show counts."""
        import duckdb

        from subprime.data.store import ensure_schema, log_refresh

        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        ensure_schema(conn)
        log_refresh(conn, scheme_count=42, nav_count=1234)
        conn.close()

        monkeypatch.setattr("subprime.cli.DB_PATH", db_path)
        result = runner.invoke(app, ["data", "stats"])
        assert result.exit_code == 0
        assert "42" in result.output
        assert "1234" in result.output or "1,234" in result.output

    def test_data_refresh_help(self):
        result = runner.invoke(app, ["data", "refresh", "--help"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to see them fail**

```bash
uv run pytest tests/test_functional.py::TestCLIData -v
```

Expected: FAIL — `data` command group doesn't exist.

- [ ] **Step 3: Add the data sub-command group to `src/subprime/cli.py`**

In `src/subprime/cli.py`, after the import section (near `DB_PATH` is imported or defined), add the import:

```python
from subprime.core.config import DB_PATH
```

Then append before `if __name__ == "__main__":`:

```python
data_app = typer.Typer(name="data", help="Manage the local fund data store.")
app.add_typer(data_app, name="data")


@data_app.command("refresh")
def data_refresh() -> None:
    """Download the latest mutual fund dataset and rebuild the local store."""
    import duckdb

    from subprime.data.ingest import refresh as run_refresh
    from subprime.data.store import ensure_schema
    from subprime.data.universe import build_universe
    from subprime.core.config import DATA_DIR

    try:
        _console.print("[dim]Downloading dataset (this may take a few minutes)...[/dim]")
        conn = duckdb.connect(str(DB_PATH))
        ensure_schema(conn)
        stats = asyncio.run(run_refresh(conn, DATA_DIR))
        _console.print(
            f"[green]Loaded[/green] {stats['scheme_count']:,} schemes, "
            f"{stats['nav_count']:,} NAV records, "
            f"{stats['returns_count']:,} computed returns."
        )
        _console.print("[dim]Building curated fund universe...[/dim]")
        universe_count = build_universe(conn)
        _console.print(f"[green]Universe ready:[/green] {universe_count} funds curated.")
        conn.close()
    except KeyboardInterrupt:
        _console.print("\n[dim]Interrupted.[/dim]")
        raise typer.Exit(0)
    except Exception as exc:
        logger.exception("data refresh failed")
        _console.print(f"\n[bold red]Error:[/bold red] {exc}")
        _console.print(f"[dim]Full traceback logged to {LOG_FILE}[/dim]")
        raise typer.Exit(1)


@data_app.command("stats")
def data_stats() -> None:
    """Show the current state of the local fund data store."""
    import duckdb

    from subprime.data.store import get_refresh_stats

    if not DB_PATH.exists():
        _console.print("[yellow]No data store found.[/yellow]")
        _console.print(f"Run [bold]subprime data refresh[/bold] to populate it.")
        return

    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        stats = get_refresh_stats(conn)
        if stats is None:
            _console.print("[yellow]Data store exists but no refreshes recorded yet.[/yellow]")
            return

        schemes_total = conn.execute("SELECT COUNT(*) FROM schemes").fetchone()[0]
        returns_total = conn.execute("SELECT COUNT(*) FROM fund_returns").fetchone()[0]
        universe_total = conn.execute("SELECT COUNT(*) FROM fund_universe").fetchone()[0]

        _console.print(f"\n[bold]Subprime Data Store[/bold]  ({DB_PATH})")
        _console.print(f"  Last refreshed : {stats['refreshed_at']}")
        _console.print(f"  Schemes        : {schemes_total:,}")
        _console.print(f"  NAV records    : {stats['nav_count']:,}")
        _console.print(f"  Computed returns: {returns_total:,}")
        _console.print(f"  Curated universe: {universe_total:,}")
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_functional.py::TestCLIData -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Verify the CLI shows the new group**

```bash
uv run subprime --help
uv run subprime data --help
uv run subprime data stats
```

Expected: `data` appears in the top-level command list. `data --help` shows `refresh` and `stats` sub-commands. `data stats` reports "No data store found."

- [ ] **Step 6: Run full suite**

```bash
uv run pytest -q
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/subprime/cli.py tests/test_functional.py
git commit -m "feat(cli): add 'subprime data refresh' and 'subprime data stats'"
```

---

### Task 8: Functional test for universe-aware plan generation

**Files:**
- Modify: `tests/test_functional.py`

- [ ] **Step 1: Add a test for generate_plan with a populated DB**

Append to `tests/test_functional.py`:

```python
# ===========================================================================
# Advisor with populated universe
# ===========================================================================


class TestAdvisorWithUniverse:
    async def test_plan_generation_loads_universe_from_db(self, tmp_path, monkeypatch):
        """When a DuckDB exists, generate_plan should inject the universe into system prompt."""
        import duckdb

        from subprime.data.store import ensure_schema
        from subprime.data.universe import build_universe

        db_path = tmp_path / "subprime.duckdb"
        conn = duckdb.connect(str(db_path))
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO schemes (amfi_code, name, amc, scheme_category, average_aum_cr) "
            "VALUES ('119551', 'UTI Nifty 50 Index Fund', 'UTI Mutual Fund', "
            "'Equity Scheme - Index Fund', 12000.0)"
        )
        conn.execute(
            "INSERT INTO fund_returns (amfi_code, returns_1y, returns_3y, returns_5y, last_computed_at) "
            "VALUES ('119551', 11.5, 13.2, 14.1, CURRENT_TIMESTAMP)"
        )
        build_universe(conn)
        conn.close()

        # Point the planner at our test DB
        monkeypatch.setattr("subprime.advisor.planner.DB_PATH", db_path)

        # Capture the system prompt by spying on create_advisor
        captured = {}

        def fake_create_advisor(*, prompt_hooks=None, universe_context=None, model=None):
            captured["universe_context"] = universe_context
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=MagicMock(output=_fake_plan()))
            return mock_agent

        monkeypatch.setattr("subprime.advisor.planner.create_advisor", fake_create_advisor)

        from subprime.advisor.planner import generate_plan

        profile = InvestorProfile(
            id="test", name="Test", age=30, risk_appetite="moderate",
            investment_horizon_years=10, monthly_investible_surplus_inr=10000,
            existing_corpus_inr=0, liabilities_inr=0,
            financial_goals=["Save"], life_stage="Mid career", tax_bracket="new_regime",
        )

        await generate_plan(profile)

        ctx = captured["universe_context"]
        assert ctx is not None
        assert "UTI Nifty 50" in ctx
        assert "Index" in ctx
```

- [ ] **Step 2: Run test**

```bash
uv run pytest tests/test_functional.py::TestAdvisorWithUniverse -v
```

Expected: PASS.

- [ ] **Step 3: Run full suite**

```bash
uv run pytest -q
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_functional.py
git commit -m "test: verify generate_plan injects universe from DuckDB"
```

---

### Task 9: Update Dockerfile and Nomad job to mount data volume

**Files:**
- Modify: `Dockerfile`
- Modify: `/home/agent/projects/nomad/jobs/subprime.tf`

- [ ] **Step 1: Update Dockerfile to create data directory**

In `Dockerfile`, before the `CMD` line, add:

```dockerfile
# Ensure data/conversations dirs exist (volumes mount over these)
RUN mkdir -p /app/data /app/conversations
```

Also add an `ENV` for the DB path so it lives in the mounted volume:

```dockerfile
ENV SUBPRIME_DATA_DIR=/app/data
```

Full relevant snippet:

```dockerfile
# ... (previous RUN uv pip install) ...

ENV GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=8091 \
    PYTHONUNBUFFERED=1 \
    SUBPRIME_DATA_DIR=/app/data

RUN mkdir -p /app/data /app/conversations

EXPOSE 8091

CMD ["python", "-c", "from apps.web.app import CSS, create_app; import os; create_app().launch(server_name=os.environ.get('GRADIO_SERVER_NAME', '0.0.0.0'), server_port=int(os.environ.get('GRADIO_SERVER_PORT', '8091')), css=CSS)"]
```

- [ ] **Step 2: Make `core/config.py` respect the env var**

In `src/subprime/core/config.py`, change the `DATA_DIR` line to:

```python
import os

DATA_DIR = Path(os.environ.get("SUBPRIME_DATA_DIR", str(Path.home() / ".subprime" / "data")))
DB_PATH = DATA_DIR / "subprime.duckdb"
```

- [ ] **Step 3: Run tests to confirm still green**

```bash
uv run pytest -q
```

Expected: All tests pass (the existing tests don't set SUBPRIME_DATA_DIR, they use tmp_path via monkeypatch).

- [ ] **Step 4: Update the Nomad job to mount the data volume**

Edit `/home/agent/projects/nomad/jobs/subprime.tf`. Replace the `volume_mount` block with two mounts (data + conversations), sharing the same host volume:

```hcl
        volume "subprime_data" {
          type      = "host"
          source    = "subprime_data"
          read_only = false
        }

        task "subprime" {
          driver = "docker"

          config {
            image        = "subprime:local"
            network_mode = "host"
          }

          env {
            ANTHROPIC_API_KEY   = "${var.subprime_anthropic_api_key}"
            GRADIO_SERVER_NAME  = "127.0.0.1"
            GRADIO_SERVER_PORT  = "${local.ports.subprime}"
            SUBPRIME_DATA_DIR   = "/app/data"
          }

          volume_mount {
            volume      = "subprime_data"
            destination = "/app"
          }
```

Rationale: mount the whole host volume at `/app/subprime_data` is clumsier — simpler to mount it at `/app` so both `/app/data` and `/app/conversations` live inside it. But that would overlay the container's app code. Instead, keep the existing mount at `/app/conversations` and add a second subdirectory for data:

Actually, the cleanest fix: use a single mount at a distinct path and point both `SUBPRIME_DATA_DIR` and the conversations directory at subdirs of it.

Revert and use this simpler approach:

```hcl
          volume_mount {
            volume      = "subprime_data"
            destination = "/app/state"
          }

          env {
            ANTHROPIC_API_KEY   = "${var.subprime_anthropic_api_key}"
            GRADIO_SERVER_NAME  = "127.0.0.1"
            GRADIO_SERVER_PORT  = "${local.ports.subprime}"
            SUBPRIME_DATA_DIR   = "/app/state/data"
          }
```

Also update `apps/web/app.py` to set `CONVERSATIONS_DIR = Path(os.environ.get("SUBPRIME_CONVERSATIONS_DIR", "conversations"))` — but we already save to a relative `conversations/` dir. For now, keep conversations at its existing relative path; only the DuckDB file needs the volume. Revert to a cleaner single mount:

```hcl
          env {
            ANTHROPIC_API_KEY   = "${var.subprime_anthropic_api_key}"
            GRADIO_SERVER_NAME  = "127.0.0.1"
            GRADIO_SERVER_PORT  = "${local.ports.subprime}"
            SUBPRIME_DATA_DIR   = "/app/state/data"
          }

          volume_mount {
            volume      = "subprime_data"
            destination = "/app/state"
          }
```

Final desired file — overwrite with:

```hcl
resource "nomad_job" "subprime" {
  jobspec = <<-EOT
    job "subprime" {
      datacenters = ["dc1"]
      type        = "service"

      group "subprime" {
        count = 0

        network {
          mode = "host"
        }

        volume "subprime_data" {
          type      = "host"
          source    = "subprime_data"
          read_only = false
        }

        task "subprime" {
          driver = "docker"

          config {
            image        = "subprime:local"
            network_mode = "host"
          }

          env {
            ANTHROPIC_API_KEY  = "${var.subprime_anthropic_api_key}"
            GRADIO_SERVER_NAME = "127.0.0.1"
            GRADIO_SERVER_PORT = "${local.ports.subprime}"
            SUBPRIME_DATA_DIR  = "/app/state/data"
          }

          volume_mount {
            volume      = "subprime_data"
            destination = "/app/state"
          }

          resources {
            cpu    = 500
            memory = 768
          }
        }
      }
    }
  EOT
}
```

- [ ] **Step 5: Commit the subprime repo changes (Dockerfile + config)**

```bash
git add Dockerfile src/subprime/core/config.py
git commit -m "feat(deploy): SUBPRIME_DATA_DIR env var for DuckDB location"
```

- [ ] **Step 6: Commit the Nomad repo change**

```bash
cd /home/agent/projects/nomad
git add jobs/subprime.tf
git commit -m "feat(subprime): mount data volume at /app/state, add SUBPRIME_DATA_DIR env"
```

---

### Task 10: Documentation update

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/data-flow.md`
- Modify: `docs/roadmap.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Mark M2 items as done in `docs/roadmap.md`**

Find the M2 section and mark off completed items:

```markdown
## M2: Data Layer + Polish

- [x] DuckDB as local data store for fund universe and historical returns
- [x] InertExpert2911/Mutual_Fund_Data GitHub dataset integration
- [x] `subprime data refresh` / `subprime data stats` commands
- [x] Curated fund universe injected into advisor system prompt (RAG)
- [ ] PDF export of investment plans
- [ ] Improved error handling and retry logic for API calls
```

- [ ] **Step 2: Update `docs/architecture.md`**

In the data module section, replace the existing data layer description with:

```markdown
### data — MF data layer

Two complementary data sources:

1. **DuckDB store** (primary) — Curated fund universe built from the
   InertExpert2911/Mutual_Fund_Data GitHub dataset. Contains scheme details,
   20M+ historical NAV records, computed 1y/3y/5y returns, and a top-N-per-category
   curated universe ranked by 5y CAGR.
2. **mfdata.in API** (real-time) — Live NAV, current details, holdings.
   Used for verification before finalizing recommendations.

Files:
- `store.py` — DuckDB connection, schema, refresh log
- `ingest.py` — Download GitHub dataset, load CSV/parquet, compute returns
- `universe.py` — Curate top funds per category, render as markdown context
- `client.py` — Async httpx wrapper for mfdata.in
- `tools.py` — PydanticAI tools: search_funds_universe (DuckDB), get_fund_performance (live), compare_funds (live)
```

- [ ] **Step 3: Update `docs/data-flow.md`**

Add a section at the top describing the RAG injection:

```markdown
## Fund Universe Injection (RAG)

Before plan generation, the advisor agent's system prompt is augmented
with a curated fund universe rendered as markdown. This gives the LLM
broad market knowledge at the start so it can reason about fund selection
without an initial blind search.

```
generate_plan(profile)
   ↓
_load_universe_context()   ← reads from ~/.subprime/data/subprime.duckdb
   ↓
create_advisor(universe_context=text)   ← text appended to system prompt
   ↓
agent.run(...)   ← LLM uses the universe + tool calls for details
```

The universe is rebuilt via `subprime data refresh`.
```

- [ ] **Step 4: Update `CLAUDE.md`**

Find the data module description and update it to match the new structure.

- [ ] **Step 5: Run full suite one more time**

```bash
uv run pytest -q
```

Expected: All tests pass.

- [ ] **Step 6: Commit docs**

```bash
git add docs/ CLAUDE.md
git commit -m "docs: document M2 RAG data layer"
```

---

### Task 11: Push everything

- [ ] **Step 1: Run full suite**

```bash
uv run pytest -q
```

Expected: All tests pass, 0 failures.

- [ ] **Step 2: Push subprime repo**

```bash
git push origin main
```

- [ ] **Step 3: Push nomad repo**

```bash
cd /home/agent/projects/nomad && git push origin main
```

- [ ] **Step 4: Deploy new version (manual)**

After merging, rebuild Docker image and roll the Nomad job:

```bash
sudo docker build -t subprime:local /home/agent/projects/subprime
cd /home/agent/projects/nomad/jobs && terraform apply -auto-approve -target=nomad_job.subprime
```

Then populate the data store on the server:

```bash
docker exec -it <subprime-container> python -m subprime.cli data refresh
```

(Or `subprime data refresh` via the task exec shell.)
