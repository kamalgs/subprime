"""Harvest existing experiment results for fine-tuning data.

Walks a results directory tree (default: research/results/runs/), loads
every JSON record where condition is 'lynch' or 'bogle', and dedupes on
(persona_id, condition, model) keeping the most recent timestamp.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from subprime.core.models import InvestmentPlan


class HarvestedRecord(BaseModel):
    """One persona × condition × model plan, lifted from a results JSON file."""

    persona_id: str
    condition: str  # 'lynch' or 'bogle'
    model: str
    plan: InvestmentPlan
    aps_score: float
    timestamp: datetime
    source_path: Path


_PHILOSOPHY_CONDITIONS = {"lynch", "bogle"}


def _iter_json_files(root: Path) -> Iterable[Path]:
    yield from root.rglob("*.json")


def _load_record(path: Path) -> HarvestedRecord | None:
    """Return a HarvestedRecord if the file contains a Lynch/Bogle plan, else None."""
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    condition = data.get("condition")
    if condition not in _PHILOSOPHY_CONDITIONS:
        return None

    try:
        plan = InvestmentPlan.model_validate(data["plan"])
    except Exception:
        return None

    aps = data.get("aps") or {}
    # composite_aps is in [0, 1]
    aps_score = aps.get("composite_aps")
    if aps_score is None:
        return None

    ts_raw = data.get("timestamp")
    if not ts_raw:
        return None
    timestamp = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))

    return HarvestedRecord(
        persona_id=data["persona_id"],
        condition=condition,
        model=data.get("model", "unknown"),
        plan=plan,
        aps_score=float(aps_score),
        timestamp=timestamp,
        source_path=path,
    )


def harvest_records(root: Path) -> list[HarvestedRecord]:
    """Walk `root` and return deduped Lynch/Bogle records.

    Dedupe key: (persona_id, condition, model). On collision, the record
    with the latest timestamp wins.
    """
    seen: dict[tuple[str, str, str], HarvestedRecord] = {}
    for path in _iter_json_files(root):
        rec = _load_record(path)
        if rec is None:
            continue
        key = (rec.persona_id, rec.condition, rec.model)
        prev = seen.get(key)
        if prev is None or rec.timestamp > prev.timestamp:
            seen[key] = rec
    return list(seen.values())
