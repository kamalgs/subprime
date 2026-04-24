"""Tests for subprime.core.tempfiles — pdf_workspace + scrubber."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from subprime.core.tempfiles import _scrub_once, pdf_workspace


def _touch_old(path: Path, mtime: float) -> None:
    path.write_bytes(b"stale")
    os.utime(path, (mtime, mtime))


def test_pdf_workspace_writes_and_unlinks() -> None:
    """The tempfile exists inside the context and is gone after."""
    seen_path: list[Path] = []
    with pdf_workspace(b"hello-pdf") as path:
        p = Path(path)
        seen_path.append(p)
        assert p.exists()
        assert p.read_bytes() == b"hello-pdf"
        assert p.name.startswith("subprime-")
        assert p.name.endswith(".pdf")
    assert not seen_path[0].exists(), "tempfile should be unlinked on exit"


def test_pdf_workspace_unlinks_on_exception() -> None:
    """Delete must happen even when the block raises."""
    seen_path: list[Path] = []

    class _Boom(Exception):
        pass

    try:
        with pdf_workspace(b"x") as path:
            seen_path.append(Path(path))
            raise _Boom()
    except _Boom:
        pass
    assert not seen_path[0].exists()


def test_scrub_once_removes_old_files() -> None:
    tmpdir = Path(tempfile.gettempdir())
    stale = tmpdir / "subprime-stale-test.pdf"
    fresh = tmpdir / "subprime-fresh-test.pdf"
    _touch_old(stale, time.time() - 3600)
    _touch_old(fresh, time.time())
    try:
        purged = _scrub_once(max_age_seconds=600)
        assert purged >= 1
        assert not stale.exists()
        assert fresh.exists(), "fresh file should survive"
    finally:
        for p in (stale, fresh):
            p.unlink(missing_ok=True)


def test_scrub_once_skips_non_matching_prefix() -> None:
    tmpdir = Path(tempfile.gettempdir())
    other = tmpdir / "not-ours-test.pdf"
    _touch_old(other, time.time() - 3600)
    try:
        _scrub_once(max_age_seconds=600)
        assert other.exists(), "non-subprime tempfiles must not be touched"
    finally:
        other.unlink(missing_ok=True)


def test_scrub_once_tolerates_missing_file() -> None:
    assert _scrub_once(max_age_seconds=600) == 0
