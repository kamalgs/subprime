"""Temporary-file hygiene — shared by every module that spills bytes to disk.

Two pieces:

  1. ``pdf_workspace(pdf_bytes)`` — context manager that writes ``pdf_bytes``
     to a ``subprime-*.pdf`` tempfile, yields the path as ``str``, and
     unlinks on exit (normal or exceptional).
  2. ``run_scrubber()`` — long-running coroutine launched from the FastAPI
     lifespan. Sweeps ``/tmp/subprime-*.pdf`` every N seconds and deletes
     anything older than the max age. Safety net for crash paths where the
     context manager never got to run its __exit__.

Every caller that writes user-uploaded bytes to disk should go through
``pdf_workspace`` rather than opening ``tempfile.NamedTemporaryFile``
directly — that way the prefix, delete flag, and scrubbing pattern stay
in one place.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


_TMPDIR = Path(tempfile.gettempdir())
_PREFIX = "subprime-"
_SUFFIX = ".pdf"
_GLOB = f"{_PREFIX}*{_SUFFIX}"


@contextmanager
def pdf_workspace(pdf_bytes: bytes) -> Iterator[str]:
    """Context manager yielding a filesystem path to *pdf_bytes*.

    The underlying ``tempfile.NamedTemporaryFile`` uses ``delete=True`` so
    the path is unlinked on context exit — including when the caller
    raises. Prefix is fixed so the scrubber can identify and clean up
    anything that leaks past us (e.g. SIGKILL mid-parse).

    Callers:
        with pdf_workspace(bytes_from_upload) as path:
            parse_library.read(path, password=...)
    """
    with tempfile.NamedTemporaryFile(prefix=_PREFIX, suffix=_SUFFIX, delete=True) as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        yield str(Path(tmp.name))


def _scrub_once(max_age_seconds: float) -> int:
    cutoff = time.time() - max_age_seconds
    purged = 0
    for p in _TMPDIR.glob(_GLOB):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                purged += 1
        except FileNotFoundError:
            pass  # race with another cleanup path — fine
        except Exception:
            logger.exception("scrubber: unlink failed for %s", p.name)
    return purged


async def run_scrubber(
    *,
    interval_seconds: float = 300.0,
    max_age_seconds: float = 600.0,
) -> None:
    """Sweep leftover PDF tempfiles every *interval_seconds*.

    Launch from the FastAPI lifespan:
        task = asyncio.create_task(run_scrubber())
        ...
        task.cancel(); await task

    Defaults: run every 5 min, drop anything ≥10 min old. The age window
    is generous so live requests are never disturbed — only actual leaks.
    """
    while True:
        try:
            purged = _scrub_once(max_age_seconds)
            if purged:
                logger.info("scrubber: removed %d leftover tempfile(s)", purged)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scrubber: iteration failed — continuing")
        await asyncio.sleep(interval_seconds)
