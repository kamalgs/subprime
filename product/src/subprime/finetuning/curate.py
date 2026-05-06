"""Curate harvested records: filter by teacher + APS threshold, split train/val."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Iterable

import yaml
from pydantic import BaseModel

from subprime.finetuning.harvest import HarvestedRecord


_DEFAULT_TEACHERS_PATH = Path(__file__).parent / "artifacts" / "teachers.yaml"


class CurateConfig(BaseModel):
    """Curation thresholds. APS values are in [0, 1]."""

    teacher_substrings: list[str]
    lynch_max_aps: float = 0.35
    bogle_min_aps: float = 0.75
    min_per_variant: int = 0  # 0 = no enforcement (used in unit tests)


def load_teacher_substrings(path: Path | None = None) -> list[str]:
    p = path or _DEFAULT_TEACHERS_PATH
    data = yaml.safe_load(p.read_text())
    return list(data.get("teachers", []))


def _matches_teacher(model: str, substrings: Iterable[str]) -> bool:
    return any(sub in model for sub in substrings)


def _passes_aps(record: HarvestedRecord, cfg: CurateConfig) -> bool:
    if record.condition == "lynch":
        return record.aps_score <= cfg.lynch_max_aps
    if record.condition == "bogle":
        return record.aps_score >= cfg.bogle_min_aps
    return False


def curate(records: list[HarvestedRecord], cfg: CurateConfig) -> list[HarvestedRecord]:
    """Apply teacher and APS-direction filters. Raise if any variant falls below the floor."""
    kept = [
        r
        for r in records
        if _matches_teacher(r.model, cfg.teacher_substrings) and _passes_aps(r, cfg)
    ]

    if cfg.min_per_variant > 0:
        for variant in ("lynch", "bogle"):
            n = sum(1 for r in kept if r.condition == variant)
            if n < cfg.min_per_variant:
                raise ValueError(
                    f"{variant} dataset below minimum: {n} < {cfg.min_per_variant}. "
                    f"Loosen APS threshold or expand teacher allow-list."
                )
    return kept


def split_train_val(
    records: list[HarvestedRecord],
    val_fraction: float = 0.1,
    seed: int = 42,
) -> tuple[list[HarvestedRecord], list[HarvestedRecord]]:
    """Stratify by persona: no persona appears in both splits.

    Personas are sorted then shuffled with `seed` for determinism.
    """
    personas = sorted({r.persona_id for r in records})
    rng = random.Random(seed)
    rng.shuffle(personas)
    n_val = max(1, int(len(personas) * val_fraction))
    val_personas = set(personas[:n_val])
    train = [r for r in records if r.persona_id not in val_personas]
    val = [r for r in records if r.persona_id in val_personas]
    return train, val
