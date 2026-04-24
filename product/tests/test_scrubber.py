"""Tests for the tempfile scrubber."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from subprime.data._scrubber import _scrub_once


def _touch_old(path: Path, mtime: float) -> None:
    path.write_bytes(b"stale")
    os.utime(path, (mtime, mtime))


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
    """Other tempfiles in /tmp are untouched."""
    tmpdir = Path(tempfile.gettempdir())
    other = tmpdir / "not-ours-test.pdf"
    _touch_old(other, time.time() - 3600)
    try:
        _scrub_once(max_age_seconds=600)
        assert other.exists(), "non-subprime tempfiles must not be touched"
    finally:
        other.unlink(missing_ok=True)


def test_scrub_once_tolerates_missing_file() -> None:
    """Race where the file disappears between glob and unlink is fine."""
    # No matching files created — should just return 0.
    assert _scrub_once(max_age_seconds=600) == 0
