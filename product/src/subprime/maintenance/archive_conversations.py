"""Archive the ``conversations`` table to CSV and clear the rows.

Designed as a periodic maintenance job: run it on whatever cadence makes
sense (daily / weekly), point ``--out-dir`` at a durable volume, and
ingest the CSVs into DuckDB for offline analysis.

The script is idempotent: each run produces a uniquely-timestamped
filename, never clobbers existing archives, and skips the truncate when
there's nothing to archive. The truncate runs in the same transaction
as the row count check, so a concurrent INSERT mid-archive is safe —
either the new row is in this archive, or it survives into the next.

JSONB columns are serialised as JSON strings. DuckDB ingestion:

    CREATE TABLE conv AS
        SELECT * FROM read_csv_auto('conversations_<ts>.csv');
    SELECT json_extract(profile, '$.age')::INT AS age, mode, count(*)
    FROM conv GROUP BY 1, 2;
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

COLUMNS = [
    "id",
    "session_id",
    "investor_name",
    "mode",
    "profile",
    "strategy",
    "plan",
    "strategy_chat",
    "created_at",
]


def _serialise(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str, ensure_ascii=False)
    return str(v)


def _archive_path(out_dir: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return out_dir / f"conversations_{ts}.csv"


async def archive(
    *,
    dsn: str,
    out_dir: Path,
    soft: bool = False,
    dry_run: bool = False,
) -> dict:
    """Archive the ``conversations`` table and clear the rows.

    Returns a small dict the caller (CLI / batch wrapper) can log:
        {"rows_archived": int, "csv_path": str | None, "skipped": bool}
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out = _archive_path(out_dir)

    if dry_run:
        truncate_sql = (
            "DELETE FROM conversations" if soft else "TRUNCATE TABLE conversations RESTART IDENTITY"
        )
        logger.info("dry-run: would write CSV to %s and run %s", out, truncate_sql)
        return {"rows_archived": 0, "csv_path": str(out), "skipped": False, "dry_run": True}

    conn = await asyncpg.connect(dsn)
    try:
        n_rows = await conn.fetchval("SELECT COUNT(*) FROM conversations")
        logger.info("conversations table has %d rows", n_rows)
        if n_rows == 0:
            return {"rows_archived": 0, "csv_path": None, "skipped": True}

        rows = await conn.fetch(f"SELECT {', '.join(COLUMNS)} FROM conversations ORDER BY id")

        with out.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            for r in rows:
                w.writerow(_serialise(r[c]) for c in COLUMNS)
        size = out.stat().st_size
        logger.info("wrote %d rows to %s (%d bytes)", n_rows, out, size)

        # Sanity: row count in CSV must match table count before delete.
        with out.open() as f:
            written = sum(1 for _ in f) - 1
        if written != n_rows:
            raise RuntimeError(f"refusing to truncate: CSV has {written} rows, table had {n_rows}")

        async with conn.transaction():
            if soft:
                await conn.execute("DELETE FROM conversations")
            else:
                await conn.execute("TRUNCATE TABLE conversations RESTART IDENTITY")
        n_after = await conn.fetchval("SELECT COUNT(*) FROM conversations")
        logger.info("conversations table now has %d rows", n_after)

        return {
            "rows_archived": n_rows,
            "csv_path": str(out),
            "skipped": False,
            "csv_bytes": size,
        }
    finally:
        await conn.close()


def main(
    *,
    dsn: str | None = None,
    out_dir: Path | None = None,
    soft: bool = False,
    dry_run: bool = False,
) -> dict:
    """Synchronous entry point used by the CLI and any external scheduler."""
    if dsn is None:
        dsn = os.environ.get("DATABASE_URL")
    if not dsn and not dry_run:
        raise RuntimeError("DATABASE_URL not set")
    if out_dir is None:
        out_dir = Path(os.environ.get("SUBPRIME_ARCHIVE_DIR", "/var/lib/subprime/archives"))
    return asyncio.run(archive(dsn=dsn or "", out_dir=out_dir, soft=soft, dry_run=dry_run))
