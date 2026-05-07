"""Disk-backed orchestration for synthesising the Stage-2 ablation corpus.

The CLI command `subprime ft synth-corpus` is glue around these helpers:

- ``load_personas_file`` / ``append_personas_file`` — chunked persona generation
  with crash resume.
- ``save_batch_pointer`` / ``load_batch_pointer`` — persist a submitted batch_id
  immediately so polling can resume after a crash.
- ``write_synth_jsonl`` — serialise SynthRecords to JSONL.

Network paths (LLM calls + Anthropic batch API) live in ``personas_gen.py`` and
``synthesize.py``; this module is the on-disk plumbing on top.
"""

from __future__ import annotations

import json
from pathlib import Path

from subprime.core.models import InvestorProfile
from subprime.finetuning.synthesize import SynthRecord


# ---------------------------------------------------------------------------
# Personas (chunked, append-only)
# ---------------------------------------------------------------------------


def load_personas_file(path: Path) -> list[InvestorProfile]:
    """Load existing personas.json (a JSON array). Empty list if absent."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    return [InvestorProfile.model_validate(row) for row in raw]


def append_personas_file(path: Path, new_profiles: list[InvestorProfile]) -> int:
    """Append profiles to ``path`` (a JSON array). Creates the file if missing.

    Returns the new total count.
    """
    existing = load_personas_file(path)
    combined = existing + list(new_profiles)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [p.model_dump(mode="json") for p in combined],
            indent=2,
            ensure_ascii=False,
        )
    )
    return len(combined)


def next_persona_id(existing: list[InvestorProfile], offset: int = 0) -> str:
    """Return the next sequential ID after the highest seen ``G###`` (zero-padded)."""
    nums: list[int] = []
    for p in existing:
        if p.id.startswith("G") and p.id[1:].isdigit():
            nums.append(int(p.id[1:]))
    n = (max(nums) if nums else 0) + 1 + offset
    return f"G{n:03d}"


def renumber_chunk(
    chunk: list[InvestorProfile], existing: list[InvestorProfile]
) -> list[InvestorProfile]:
    """Force IDs in ``chunk`` to be sequential, after the highest existing one.

    Sonnet sometimes restarts numbering at G001 in fresh chunks. We rewrite the
    IDs so the on-disk personas.json never has duplicates.
    """
    out: list[InvestorProfile] = []
    base = existing[:]
    for i, p in enumerate(chunk):
        new_id = next_persona_id(base, offset=i)
        if p.id != new_id:
            p = p.model_copy(update={"id": new_id})
        out.append(p)
    return out


# ---------------------------------------------------------------------------
# Batch pointer (resume across restarts)
# ---------------------------------------------------------------------------


def save_batch_pointer(path: Path, batch_id: str, *, hook: str, n_requests: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"batch_id": batch_id, "hook": hook, "n_requests": n_requests},
            indent=2,
        )
    )


def load_batch_pointer(path: Path) -> str | None:
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("batch_id")


# ---------------------------------------------------------------------------
# SynthRecord JSONL persistence
# ---------------------------------------------------------------------------


def write_synth_jsonl(records: list[SynthRecord], path: Path) -> int:
    """Write one SynthRecord per line. Skips rows where ``parse_ok=False``.

    Returns count actually written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w") as f:
        for r in records:
            if not r.parse_ok:
                continue
            f.write(r.model_dump_json() + "\n")
            n += 1
    return n


def read_synth_jsonl(path: Path) -> list[SynthRecord]:
    """Load SynthRecord JSONL written by ``write_synth_jsonl``."""
    rows: list[SynthRecord] = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(SynthRecord.model_validate_json(line))
    return rows


# ---------------------------------------------------------------------------
# Build dataset from synth source
# ---------------------------------------------------------------------------


def build_synth_dataset_for_variant(
    *,
    variant: str,
    synth_dir: Path,
    out_dir: Path,
    out_suffix: str,
    variant_size: int,
    val_fraction: float,
    seed: int = 42,
) -> dict[str, int]:
    """Build train/val JSONLs for ONE variant from synthesised plans on disk.

    - Reads ``synth_dir/<variant>_synth.jsonl`` + ``synth_dir/personas.json``.
    - Random-samples down to ``variant_size`` records (seed=42 by default).
    - Splits stratified-by-persona: no persona appears in both train & val.
    - Writes ``<variant>{out_suffix}_train.jsonl`` / ``_val.jsonl`` under ``out_dir``.

    No teacher-allow-list, no APS-direction filter — synth records were
    generated with the hard hook explicitly and are kept verbatim.
    """
    import random

    from subprime.finetuning.format import write_jsonl_plans

    synth_path = synth_dir / f"{variant}_synth.jsonl"
    personas_path = synth_dir / "personas.json"
    if not synth_path.exists():
        raise FileNotFoundError(f"missing synth jsonl: {synth_path}")
    if not personas_path.exists():
        raise FileNotFoundError(f"missing personas file: {personas_path}")

    profiles_by_id = {p.id: p for p in load_personas_file(personas_path)}
    records = [r for r in read_synth_jsonl(synth_path) if r.parse_ok and r.plan]
    records = [r for r in records if r.persona_id in profiles_by_id]

    rng = random.Random(seed)
    if variant_size > 0 and len(records) > variant_size:
        records = sorted(records, key=lambda r: r.persona_id)
        records = rng.sample(records, variant_size)

    # Stratified persona split
    personas = sorted({r.persona_id for r in records})
    rng2 = random.Random(seed)
    rng2.shuffle(personas)
    n_val = max(1, int(len(personas) * val_fraction))
    val_personas = set(personas[:n_val])

    train_pairs: list[tuple[object, object]] = []
    val_pairs: list[tuple[object, object]] = []
    for r in records:
        prof = profiles_by_id[r.persona_id]
        target = val_pairs if r.persona_id in val_personas else train_pairs
        target.append((prof, r.plan))

    out_dir.mkdir(parents=True, exist_ok=True)
    train_path = out_dir / f"{variant}{out_suffix}_train.jsonl"
    val_path = out_dir / f"{variant}{out_suffix}_val.jsonl"
    n_train = write_jsonl_plans(train_pairs, train_path)  # type: ignore[arg-type]
    n_val_w = write_jsonl_plans(val_pairs, val_path)  # type: ignore[arg-type]
    return {"train": n_train, "val": n_val_w, "total": len(records)}
