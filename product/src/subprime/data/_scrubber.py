"""Background scrubber for leftover PDF tempfiles.

Normal-path cleanup is done by ``tempfile.NamedTemporaryFile(delete=True)``,
which unlinks on context exit even on exception. This scrubber is a
second line of defence for:

  - Process crashes between write and delete (SIGKILL, OOM)
  - Workers leaking handles we don't own (pdfminer / pypdf edge cases)
  - Prestart restarts that leave /tmp dirty

Runs every N seconds, deletes any file under ``tempfile.gettempdir()``
matching the ``subprime-*.pdf`` prefix older than ``max_age_seconds``.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)


_TMPDIR = Path(tempfile.gettempdir())
_PATTERN = "subprime-*.pdf"


def _scrub_once(max_age_seconds: float) -> int:
    cutoff = time.time() - max_age_seconds
    purged = 0
    for p in _TMPDIR.glob(_PATTERN):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                purged += 1
        except FileNotFoundError:
            pass
        except Exception:
            logger.exception("scrubber: unlink failed for %s", p.name)
    return purged


async def run_scrubber(
    *,
    interval_seconds: float = 300.0,
    max_age_seconds: float = 600.0,
) -> None:
    """Long-running coroutine — launch from the FastAPI lifespan.

    Defaults: sweep every 5 min, drop anything ≥10 min old. The window is
    deliberately larger than any realistic parse time so live requests
    aren't disturbed; it only catches actual leaks.
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
