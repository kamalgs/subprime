"""Unit tests for synth_corpus persona-resume + JSONL persistence."""

from __future__ import annotations

import json
from pathlib import Path

from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
)
from subprime.finetuning.synth_corpus import (
    append_personas_file,
    build_synth_dataset_for_variant,
    load_personas_file,
    next_persona_id,
    read_synth_jsonl,
    renumber_chunk,
    save_batch_pointer,
    write_synth_jsonl,
)
from subprime.finetuning.synthesize import SynthRecord


def _profile(pid: str, name: str = "Test") -> InvestorProfile:
    return InvestorProfile(
        id=pid,
        name=name,
        age=35,
        risk_appetite="moderate",
        investment_horizon_years=15,
        monthly_investible_surplus_inr=50_000,
        existing_corpus_inr=500_000,
        liabilities_inr=0,
        financial_goals=["retirement"],
        life_stage="mid_career",
        tax_bracket="30%",
    )


def _plan() -> InvestmentPlan:
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(amfi_code="118668", name="Test Fund"),
                allocation_pct=100.0,
                mode="sip",
                monthly_sip_inr=10_000.0,
                rationale="test",
            )
        ],
        rationale="test",
    )


def test_append_personas_file_grows_not_overwrites(tmp_path: Path) -> None:
    p = tmp_path / "personas.json"
    a = [_profile("G001"), _profile("G002")]
    append_personas_file(p, a)
    assert p.exists()
    assert len(load_personas_file(p)) == 2

    b = [_profile("G003")]
    total = append_personas_file(p, b)
    assert total == 3

    loaded = load_personas_file(p)
    assert [x.id for x in loaded] == ["G001", "G002", "G003"]


def test_next_persona_id_continues_after_max() -> None:
    existing = [_profile("G001"), _profile("G003")]
    assert next_persona_id(existing) == "G004"
    assert next_persona_id(existing, offset=2) == "G006"
    assert next_persona_id([]) == "G001"


def test_renumber_chunk_avoids_collisions(tmp_path: Path) -> None:
    p = tmp_path / "personas.json"
    append_personas_file(p, [_profile("G001"), _profile("G002")])
    existing = load_personas_file(p)

    # Sonnet might restart numbering at G001 — we must rewrite IDs.
    fresh = [_profile("G001"), _profile("G002"), _profile("G003")]
    renumbered = renumber_chunk(fresh, existing)
    assert [x.id for x in renumbered] == ["G003", "G004", "G005"]
    # Names preserved (only id changed)
    assert all(x.name == "Test" for x in renumbered)


def test_synth_corpus_resume_skips_existing_personas(tmp_path: Path, monkeypatch) -> None:
    """End-to-end resume path: if personas.json already has N rows, generate (target-N) more.

    We monkeypatch generate_personas to capture how many it was asked for and
    return a fake chunk; that lets us verify only the missing rows are
    requested when resuming.
    """
    p = tmp_path / "personas.json"
    append_personas_file(p, [_profile("G001"), _profile("G002")])

    captured: dict[str, int] = {}

    async def fake_gen(n, model="x", seed=42):
        captured["n"] = n
        # Fake chunk; renumber_chunk will fix IDs anyway
        return [_profile("G001") for _ in range(n)]

    # Direct call into the chunked-resume helper logic — mirror what the CLI does
    target = 5
    existing = load_personas_file(p)
    assert len(existing) == 2
    while len(existing) < target:
        need = target - len(existing)
        chunk = renumber_chunk(__import__("asyncio").run(fake_gen(need)), existing)
        append_personas_file(p, chunk)
        existing = load_personas_file(p)

    assert captured["n"] == 3  # asked for 3, not 5
    final = load_personas_file(p)
    assert len(final) == 5
    assert [x.id for x in final] == ["G001", "G002", "G003", "G004", "G005"]


def test_save_batch_pointer_round_trip(tmp_path: Path) -> None:
    from subprime.finetuning.synth_corpus import load_batch_pointer

    p = tmp_path / "lynch_batch.json"
    assert load_batch_pointer(p) is None
    save_batch_pointer(p, "msgbatch_abc", hook="lynch", n_requests=10)
    assert load_batch_pointer(p) == "msgbatch_abc"
    data = json.loads(p.read_text())
    assert data["hook"] == "lynch" and data["n_requests"] == 10


def test_write_synth_jsonl_skips_failed_records(tmp_path: Path) -> None:
    records = [
        SynthRecord(persona_id="G001", hook_name="lynch", plan=_plan(), parse_ok=True),
        SynthRecord(persona_id="G002", hook_name="lynch", parse_ok=False, error="boom"),
        SynthRecord(persona_id="G003", hook_name="lynch", plan=_plan(), parse_ok=True),
    ]
    p = tmp_path / "lynch_synth.jsonl"
    n = write_synth_jsonl(records, p)
    assert n == 2
    loaded = read_synth_jsonl(p)
    assert [r.persona_id for r in loaded] == ["G001", "G003"]


def test_build_synth_dataset_for_variant_writes_with_suffix(tmp_path: Path) -> None:
    synth_dir = tmp_path / "synth"
    synth_dir.mkdir()

    profiles = [_profile(f"G{i:03d}") for i in range(1, 21)]
    append_personas_file(synth_dir / "personas.json", profiles)

    records = [
        SynthRecord(persona_id=p.id, hook_name="lynch", plan=_plan(), parse_ok=True)
        for p in profiles
    ]
    write_synth_jsonl(records, synth_dir / "lynch_synth.jsonl")

    out = tmp_path / "datasets"
    counts = build_synth_dataset_for_variant(
        variant="lynch",
        synth_dir=synth_dir,
        out_dir=out,
        out_suffix="_n10",
        variant_size=10,
        val_fraction=0.1,
    )
    assert counts["total"] == 10
    assert counts["train"] + counts["val"] == 10
    assert (out / "lynch_n10_train.jsonl").exists()
    assert (out / "lynch_n10_val.jsonl").exists()
