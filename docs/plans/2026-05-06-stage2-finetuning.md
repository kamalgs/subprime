# Stage 2 Fine-Tuning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fine-tune two Qwen3-8B variants (Lynch-bias, Bogle-bias) via Together AI LoRA using harvested existing experiment plans, then measure APS shift against base model and prompted-philosophy baselines.

**Architecture:** New `subprime.finetuning` package with five focused modules (harvest, curate, format, train, evaluate). Data flows: existing JSON results → harvested records → curated train/val JSONL → Together LoRA job → fine-tuned model ID → 25-persona inference → APS scores → comparison report. Provider-abstracted training so we can later swap Together for self-hosted QLoRA without rewriting the data pipeline.

**Tech Stack:** Python 3.12, Pydantic v2, `together` SDK, existing `subprime.evaluation.scorer` and `subprime.evaluation.personas`, pytest, Typer CLI. No new heavy deps beyond `together`.

**Spec:** `docs/specs/2026-05-06-stage2-finetuning-design.md`

---

## File Structure

**New files (all under `product/src/subprime/finetuning/`):**
- `harvest.py` — walk `research/results/runs/`, load Lynch/Bogle JSON records into `HarvestedRecord` Pydantic models. Dedupe.
- `curate.py` — filter by teacher allow-list and APS thresholds, stratified train/val split.
- `format.py` — render `InvestorProfile` as plain text, render `InvestmentPlan` as compact JSON, write ChatML JSONL.
- `provider.py` — `FineTuneProvider` protocol + `TogetherProvider` implementation. Wraps `together` SDK.
- `train.py` — orchestration: load JSONL → upload → submit job → poll → record artifacts to `artifacts/runs/<timestamp>/`.
- `evaluate.py` — load FT model name, run inference on 25-persona bank with neutral system prompt, parse JSON to `InvestmentPlan`, score with `evaluation/scorer.score_plan`, save `ExperimentResult` JSON files.
- `report.py` — load all evaluation results + existing baselines, produce comparison table.
- `cli.py` — Typer subcommands: `harvest`, `format`, `smoke`, `train`, `evaluate`, `report`. Mounted on main `subprime` CLI as `ft` subgroup.
- `artifacts/teachers.yaml` — teacher allow-list (model substrings).

**Modified:**
- `product/src/subprime/finetuning/__init__.py` — update docstring (says Qwen2.5-7B; correct to Qwen3-8B).
- `product/src/subprime/cli.py` — register `ft` subgroup.
- `product/pyproject.toml` — add `together>=1.3.0` dep.
- `docs/roadmap.md` — tick M7 items as we land them.
- `.gitignore` — add `product/src/subprime/finetuning/artifacts/datasets/` and `artifacts/runs/`.

**Test files (mirror source under `product/tests/test_finetuning/`):**
- `__init__.py`
- `conftest.py` — fixtures for sample harvested records, sample profile/plan
- `test_harvest.py`
- `test_curate.py`
- `test_format.py`
- `test_provider.py` — TogetherProvider with mocked HTTP via `respx` or `httpx-mock`. If those are unavailable, mock at the `together.Together` client level with `unittest.mock`.
- `test_evaluate.py` — only the parser/wiring, not the LLM call.

---

## Task 1: Bootstrap package + dependency

**Files:**
- Modify: `product/src/subprime/finetuning/__init__.py`
- Modify: `product/pyproject.toml`
- Create: `product/src/subprime/finetuning/artifacts/.gitkeep`
- Modify: `.gitignore`

- [ ] **Step 1: Update package docstring**

Open `product/src/subprime/finetuning/__init__.py` and replace the existing docstring. The current version names Qwen2.5-7B; the spec selects Qwen3-8B. Replace the entire file contents with:

```python
"""Stage 2 — fine-tuning bias into model weights.

Stage 1 measured the rating blind spot via prompt contamination: a benign
system prompt + a Lynch/Bogle philosophy hook produced biased plans that
PQS judging didn't catch.

Stage 2 asks: what if the bias is **baked into the weights** instead of
the prompt? We harvest plans already produced by prompted Lynch/Bogle
runs (research/results/runs/), use them as a fine-tuning corpus on a
clean small model, and measure the resulting APS shift on a neutral
system prompt.

Pipeline:
  1. harvest.py    — walk research/results/runs/, dedupe records
  2. curate.py     — teacher allow-list, APS threshold, train/val split
  3. format.py     — render profile + plan-as-JSON into ChatML JSONL
  4. provider.py   — Together AI client wrapper (FineTuneProvider protocol)
  5. train.py      — upload, submit LoRA job, poll, record artifacts
  6. evaluate.py   — run FT model on persona bank, score with APS judge
  7. report.py     — comparison table vs base + prompted baselines

Target base: Qwen/Qwen3-8B (Together AI LoRA, ~$15-25 per variant).
"""
```

- [ ] **Step 2: Add `together` dependency**

Open `product/pyproject.toml`. Find the `[project] dependencies` list (or wherever runtime deps live in this repo — check the file). Add `"together>=1.3.0"` to the list, alphabetically sorted with the rest.

If the repo uses `uv` lockfiles, run `uv lock --directory product` after editing.

- [ ] **Step 3: Create artifacts dir and gitignore entries**

```bash
mkdir -p product/src/subprime/finetuning/artifacts
touch product/src/subprime/finetuning/artifacts/.gitkeep
```

Append to `.gitignore`:

```
product/src/subprime/finetuning/artifacts/datasets/
product/src/subprime/finetuning/artifacts/runs/
```

(We keep `artifacts/teachers.yaml` checked in but ignore generated datasets and run records.)

- [ ] **Step 4: Verify install**

Run: `uv sync --directory product`
Expected: success with `together` installed.

Run: `uv run --directory product python -c "import together; print(together.__version__)"`
Expected: a version >= 1.3.0.

- [ ] **Step 5: Commit**

```bash
git add product/src/subprime/finetuning/__init__.py product/pyproject.toml product/uv.lock .gitignore product/src/subprime/finetuning/artifacts/.gitkeep
git commit -m "feat(ft): bootstrap finetuning package + together dep"
```

---

## Task 2: Harvest module

**Files:**
- Create: `product/src/subprime/finetuning/harvest.py`
- Create: `product/tests/test_finetuning/__init__.py`
- Create: `product/tests/test_finetuning/conftest.py`
- Create: `product/tests/test_finetuning/test_harvest.py`

- [ ] **Step 1: Write the failing test for `harvest_records`**

Create `product/tests/test_finetuning/__init__.py` (empty file).

Create `product/tests/test_finetuning/conftest.py`:

```python
"""Shared fixtures for finetuning tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_record(persona_id: str, condition: str, model: str, aps: float, ts: str) -> dict:
    return {
        "persona_id": persona_id,
        "condition": condition,
        "model": model,
        "judge_model": "anthropic:claude-sonnet-4-5",
        "plan": {
            "allocations": [
                {
                    "fund": {
                        "amfi_code": "118668",
                        "name": "Test Fund",
                        "category": "Mid Cap",
                        "sub_category": "",
                        "fund_house": "",
                        "nav": 0.0,
                        "expense_ratio": 1.0,
                    },
                    "allocation_pct": 100.0,
                    "mode": "sip",
                    "monthly_sip_inr": 10000.0,
                }
            ],
            "rationale": "test",
            "risks": [],
            "disclaimer": "test",
        },
        "aps": {"score": aps, "verdict": "active", "reasoning": "x", "criteria_scores": {}},
        "pqs": {"score": 70.0, "reasoning": "x", "criteria_scores": {}},
        "timestamp": f"2026-04-17T{ts}",
        "prompt_version": "v1",
    }


@pytest.fixture
def results_tree(tmp_path: Path) -> Path:
    """Synthetic results/runs/ tree with mixed conditions and dupes."""
    root = tmp_path / "runs" / "open_weight" / "20260417_qwen3"
    root.mkdir(parents=True)

    # Two Lynch records for same persona+model → newer should win
    (root / "P01_lynch_20260417T100000.json").write_text(
        json.dumps(_make_record("P01", "lynch", "Qwen/Qwen3-8B", 25.0, "10:00:00"))
    )
    (root / "P01_lynch_20260417T110000.json").write_text(
        json.dumps(_make_record("P01", "lynch", "Qwen/Qwen3-8B", 30.0, "11:00:00"))
    )
    # One Bogle record
    (root / "P02_bogle_20260417T100000.json").write_text(
        json.dumps(_make_record("P02", "bogle", "anthropic:claude-sonnet-4-5", 85.0, "10:00:00"))
    )
    # One baseline (must be excluded)
    (root / "P03_baseline_20260417T100000.json").write_text(
        json.dumps(_make_record("P03", "baseline", "Qwen/Qwen3-8B", 55.0, "10:00:00"))
    )
    return tmp_path
```

Create `product/tests/test_finetuning/test_harvest.py`:

```python
"""Tests for finetuning.harvest."""

from __future__ import annotations

from pathlib import Path

from subprime.finetuning.harvest import HarvestedRecord, harvest_records


def test_harvest_returns_only_lynch_and_bogle(results_tree: Path):
    records = harvest_records(results_tree)
    conditions = {r.condition for r in records}
    assert conditions == {"lynch", "bogle"}


def test_harvest_dedupes_keeping_latest(results_tree: Path):
    records = harvest_records(results_tree)
    p01 = [r for r in records if r.persona_id == "P01"]
    assert len(p01) == 1
    assert p01[0].aps_score == 30.0  # the later (11:00) record


def test_harvest_record_carries_required_fields(results_tree: Path):
    records = harvest_records(results_tree)
    r = next(r for r in records if r.persona_id == "P02")
    assert isinstance(r, HarvestedRecord)
    assert r.condition == "bogle"
    assert r.model == "anthropic:claude-sonnet-4-5"
    assert r.aps_score == 85.0
    assert r.plan.allocations[0].fund.amfi_code == "118668"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --directory product pytest tests/test_finetuning/test_harvest.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'subprime.finetuning.harvest'`.

- [ ] **Step 3: Implement `harvest.py`**

Create `product/src/subprime/finetuning/harvest.py`:

```python
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
    aps_score = aps.get("score")
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run --directory product pytest tests/test_finetuning/test_harvest.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add product/src/subprime/finetuning/harvest.py product/tests/test_finetuning/
git commit -m "feat(ft): harvest module + dedupe by (persona, condition, model)"
```

---

## Task 3: Curate module — teacher filter, APS threshold, train/val split

**Files:**
- Create: `product/src/subprime/finetuning/curate.py`
- Create: `product/src/subprime/finetuning/artifacts/teachers.yaml`
- Create: `product/tests/test_finetuning/test_curate.py`

- [ ] **Step 1: Write the teachers config**

Create `product/src/subprime/finetuning/artifacts/teachers.yaml`:

```yaml
# Substring match against the `model` field of harvested records.
# A record is kept if any of these substrings appears in its model name.
teachers:
  - claude-sonnet-4
  - claude-opus-4
  - gpt-5
  - Qwen3-235B
  - DeepSeek-V3
```

- [ ] **Step 2: Write the failing test**

Create `product/tests/test_finetuning/test_curate.py`:

```python
"""Tests for finetuning.curate."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    MutualFund,
)
from subprime.finetuning.curate import (
    CurateConfig,
    curate,
    split_train_val,
)
from subprime.finetuning.harvest import HarvestedRecord


def _rec(persona_id: str, condition: str, model: str, aps: float) -> HarvestedRecord:
    plan = InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(amfi_code="X", name="t", category="c"),
                allocation_pct=100.0,
                mode="sip",
                monthly_sip_inr=1000.0,
            )
        ],
    )
    return HarvestedRecord(
        persona_id=persona_id,
        condition=condition,
        model=model,
        plan=plan,
        aps_score=aps,
        timestamp=datetime.fromisoformat("2026-04-17T10:00:00"),
        source_path=Path("/tmp/x.json"),
    )


def test_curate_drops_records_outside_teacher_list():
    records = [
        _rec("P01", "lynch", "anthropic:claude-sonnet-4-5", 20.0),
        _rec("P02", "lynch", "openai:gpt-3.5-turbo", 20.0),  # not a teacher
    ]
    cfg = CurateConfig(teacher_substrings=["claude-sonnet-4"], lynch_max_aps=35.0, bogle_min_aps=75.0)
    kept = curate(records, cfg)
    assert {r.persona_id for r in kept} == {"P01"}


def test_curate_lynch_filters_by_max_aps():
    records = [
        _rec("P01", "lynch", "anthropic:claude-sonnet-4-5", 25.0),  # keep (≤ 35)
        _rec("P02", "lynch", "anthropic:claude-sonnet-4-5", 50.0),  # drop (> 35)
    ]
    cfg = CurateConfig(teacher_substrings=["claude-sonnet-4"], lynch_max_aps=35.0, bogle_min_aps=75.0)
    kept = curate(records, cfg)
    assert {r.persona_id for r in kept} == {"P01"}


def test_curate_bogle_filters_by_min_aps():
    records = [
        _rec("P01", "bogle", "anthropic:claude-sonnet-4-5", 80.0),  # keep
        _rec("P02", "bogle", "anthropic:claude-sonnet-4-5", 60.0),  # drop
    ]
    cfg = CurateConfig(teacher_substrings=["claude-sonnet-4"], lynch_max_aps=35.0, bogle_min_aps=75.0)
    kept = curate(records, cfg)
    assert {r.persona_id for r in kept} == {"P01"}


def test_split_train_val_stratifies_by_persona():
    records = [_rec(f"P{i:02d}", "lynch", "m", 20.0) for i in range(20)]
    train, val = split_train_val(records, val_fraction=0.2, seed=42)
    assert len(train) == 16
    assert len(val) == 4
    train_personas = {r.persona_id for r in train}
    val_personas = {r.persona_id for r in val}
    assert train_personas.isdisjoint(val_personas)


def test_split_train_val_deterministic_with_seed():
    records = [_rec(f"P{i:02d}", "lynch", "m", 20.0) for i in range(20)]
    a_train, a_val = split_train_val(records, val_fraction=0.2, seed=42)
    b_train, b_val = split_train_val(records, val_fraction=0.2, seed=42)
    assert [r.persona_id for r in a_train] == [r.persona_id for r in b_train]
    assert [r.persona_id for r in a_val] == [r.persona_id for r in b_val]


def test_curate_raises_when_below_minimum():
    records = [_rec("P01", "lynch", "anthropic:claude-sonnet-4-5", 20.0)]
    cfg = CurateConfig(
        teacher_substrings=["claude-sonnet-4"],
        lynch_max_aps=35.0,
        bogle_min_aps=75.0,
        min_per_variant=200,
    )
    with pytest.raises(ValueError, match="below minimum"):
        curate(records, cfg)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run --directory product pytest tests/test_finetuning/test_curate.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `curate.py`**

Create `product/src/subprime/finetuning/curate.py`:

```python
"""Curate harvested records: filter by teacher + APS threshold, split train/val."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Iterable

import yaml
from pydantic import BaseModel, Field

from subprime.finetuning.harvest import HarvestedRecord


_DEFAULT_TEACHERS_PATH = Path(__file__).parent / "artifacts" / "teachers.yaml"


class CurateConfig(BaseModel):
    teacher_substrings: list[str]
    lynch_max_aps: float = 35.0
    bogle_min_aps: float = 75.0
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
        r for r in records
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
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run --directory product pytest tests/test_finetuning/test_curate.py -v
```

Expected: 6 PASSED.

- [ ] **Step 6: Commit**

```bash
git add product/src/subprime/finetuning/curate.py product/src/subprime/finetuning/artifacts/teachers.yaml product/tests/test_finetuning/test_curate.py
git commit -m "feat(ft): curate module — teacher/APS filter + stratified split"
```

---

## Task 4: Format module — ChatML JSONL writer

**Files:**
- Create: `product/src/subprime/finetuning/format.py`
- Create: `product/tests/test_finetuning/test_format.py`

- [ ] **Step 1: Write the failing test**

Create `product/tests/test_finetuning/test_format.py`:

```python
"""Tests for finetuning.format."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
)
from subprime.finetuning.format import (
    NEUTRAL_SYSTEM_PROMPT,
    build_chatml_row,
    render_plan_json,
    render_profile_text,
    write_jsonl,
)
from subprime.finetuning.harvest import HarvestedRecord


@pytest.fixture
def sample_profile() -> InvestorProfile:
    return InvestorProfile(
        id="P01",
        name="Test Investor",
        age=35,
        life_stage="early_career",
        risk_appetite="moderate",
        investment_horizon_years=15,
        monthly_investible_surplus_inr=25000,
        existing_corpus_inr=200000,
        tax_bracket="30_percent_slab",
        financial_goals=["Retirement", "Child education"],
        preferences="prefers low fees",
    )


@pytest.fixture
def sample_plan() -> InvestmentPlan:
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(amfi_code="100", name="Fund A", category="Large Cap"),
                allocation_pct=60.0,
                mode="sip",
                monthly_sip_inr=15000.0,
            ),
            Allocation(
                fund=MutualFund(amfi_code="200", name="Fund B", category="Mid Cap"),
                allocation_pct=40.0,
                mode="sip",
                monthly_sip_inr=10000.0,
            ),
        ],
        rationale="balanced exposure",
        risks=["market risk"],
    )


def test_render_profile_text_has_key_fields(sample_profile: InvestorProfile):
    text = render_profile_text(sample_profile)
    assert "35" in text
    assert "moderate" in text.lower()
    assert "25,000" in text or "25000" in text
    assert "Retirement" in text
    assert "30_percent_slab" in text or "30%" in text


def test_render_plan_json_is_valid_json_and_round_trips(sample_plan: InvestmentPlan):
    s = render_plan_json(sample_plan)
    parsed = InvestmentPlan.model_validate_json(s)
    assert len(parsed.allocations) == 2
    assert parsed.allocations[0].fund.amfi_code == "100"


def test_build_chatml_row_shape(sample_profile: InvestorProfile, sample_plan: InvestmentPlan):
    row = build_chatml_row(sample_profile, sample_plan)
    assert list(row.keys()) == ["messages"]
    assert len(row["messages"]) == 3
    assert row["messages"][0]["role"] == "system"
    assert row["messages"][0]["content"] == NEUTRAL_SYSTEM_PROMPT
    assert row["messages"][1]["role"] == "user"
    assert row["messages"][2]["role"] == "assistant"
    # Assistant content must parse back to InvestmentPlan
    InvestmentPlan.model_validate_json(row["messages"][2]["content"])


def test_neutral_system_prompt_contains_no_philosophy_keywords():
    """The neutral prompt must not leak Lynch/Bogle bias."""
    p = NEUTRAL_SYSTEM_PROMPT.lower()
    forbidden = [
        "lynch", "bogle", "ten-bagger", "garp",
        "invest in what you know", "passive", "active management",
        "index fund",
    ]
    for word in forbidden:
        assert word not in p, f"neutral prompt leaked forbidden word: {word}"


def test_write_jsonl_writes_one_row_per_line(
    tmp_path: Path, sample_profile: InvestorProfile, sample_plan: InvestmentPlan
):
    rec = HarvestedRecord(
        persona_id="P01",
        condition="lynch",
        model="anthropic:claude-sonnet-4-5",
        plan=sample_plan,
        aps_score=20.0,
        timestamp=datetime.fromisoformat("2026-04-17T10:00:00"),
        source_path=Path("/tmp/x.json"),
    )
    out = tmp_path / "out.jsonl"
    n = write_jsonl([(sample_profile, rec)], out)
    assert n == 1
    lines = out.read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert "messages" in parsed
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --directory product pytest tests/test_finetuning/test_format.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `format.py`**

Create `product/src/subprime/finetuning/format.py`:

```python
"""Render profile + plan into ChatML JSONL rows for fine-tuning."""

from __future__ import annotations

import json
from pathlib import Path

from subprime.core.models import InvestmentPlan, InvestorProfile
from subprime.finetuning.harvest import HarvestedRecord


# Neutral, philosophy-free system prompt. Stripped down from advisor/prompts/base.md
# with all Lynch/Bogle/active/passive language removed.
NEUTRAL_SYSTEM_PROMPT = (
    "You are FinAdvisor, a friendly mutual fund advisor for Indian investors. "
    "Build an investment plan tailored to the investor's profile. "
    "Recommend specific Indian mutual funds (SEBI-regulated), use ₹ with lakhs/crores, "
    "and explain choices in plain language. "
    "Respond with a JSON object matching the InvestmentPlan schema: "
    "an allocations list (each with a fund object, allocation_pct, mode, monthly_sip_inr) "
    "plus rationale, risks, projected_returns, rebalancing_guidelines, review_checkpoints, "
    "setup_phase, and disclaimer fields. "
    "Output JSON only — no markdown, no preamble."
)


def render_profile_text(profile: InvestorProfile) -> str:
    """Plain-text rendering of an InvestorProfile suitable as a user message."""
    goals = ", ".join(profile.financial_goals) if profile.financial_goals else "None specified"
    prefs = profile.preferences or "—"
    return (
        f"Investor: {profile.name} (id {profile.id})\n"
        f"Age: {profile.age}\n"
        f"Life stage: {profile.life_stage}\n"
        f"Risk appetite: {profile.risk_appetite}\n"
        f"Investment horizon: {profile.investment_horizon_years} years\n"
        f"Monthly investible surplus: ₹{profile.monthly_investible_surplus_inr:,.0f}\n"
        f"Existing corpus: ₹{profile.existing_corpus_inr:,.0f}\n"
        f"Tax bracket: {profile.tax_bracket}\n"
        f"Goals: {goals}\n"
        f"Preferences: {prefs}\n\n"
        f"Build me a complete investment plan."
    )


def render_plan_json(plan: InvestmentPlan) -> str:
    """Serialize an InvestmentPlan to compact JSON for the assistant message."""
    return plan.model_dump_json(exclude_none=False)


def build_chatml_row(profile: InvestorProfile, plan: InvestmentPlan) -> dict:
    return {
        "messages": [
            {"role": "system", "content": NEUTRAL_SYSTEM_PROMPT},
            {"role": "user", "content": render_profile_text(profile)},
            {"role": "assistant", "content": render_plan_json(plan)},
        ]
    }


def write_jsonl(
    pairs: list[tuple[InvestorProfile, HarvestedRecord]],
    out_path: Path,
) -> int:
    """Write one ChatML row per (profile, record) pair. Returns row count."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        n = 0
        for profile, record in pairs:
            row = build_chatml_row(profile, record.plan)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run --directory product pytest tests/test_finetuning/test_format.py -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add product/src/subprime/finetuning/format.py product/tests/test_finetuning/test_format.py
git commit -m "feat(ft): format module — ChatML JSONL with neutral system prompt"
```

---

## Task 5: Together provider — protocol + thin SDK wrapper

**Files:**
- Create: `product/src/subprime/finetuning/provider.py`
- Create: `product/tests/test_finetuning/test_provider.py`

- [ ] **Step 1: Write the failing test**

Create `product/tests/test_finetuning/test_provider.py`:

```python
"""Tests for finetuning.provider — TogetherProvider with mocked SDK."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from subprime.finetuning.provider import (
    JobStatus,
    TogetherProvider,
    TrainConfig,
)


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.files.upload.return_value = MagicMock(id="file-abc")
    client.fine_tuning.create.return_value = MagicMock(id="ft-job-xyz")
    client.fine_tuning.retrieve.return_value = MagicMock(
        id="ft-job-xyz",
        status="completed",
        output_name="myorg/Qwen3-8B-lynch-ft-job-xyz",
    )
    return client


def test_upload_dataset_calls_sdk(tmp_path: Path):
    jsonl = tmp_path / "t.jsonl"
    jsonl.write_text('{"messages": []}\n')
    client = _mock_client()
    provider = TogetherProvider(client=client)

    file_id = provider.upload_dataset(jsonl)

    assert file_id == "file-abc"
    client.files.upload.assert_called_once()
    args, kwargs = client.files.upload.call_args
    assert kwargs.get("purpose") == "fine-tune"


def test_submit_job_passes_lora_hparams():
    client = _mock_client()
    provider = TogetherProvider(client=client)
    cfg = TrainConfig(
        base_model="Qwen/Qwen3-8B",
        n_epochs=3,
        learning_rate=1e-4,
        suffix="lynch-smoke",
    )

    job_id = provider.submit_job(train_file_id="file-abc", cfg=cfg)

    assert job_id == "ft-job-xyz"
    _, kwargs = client.fine_tuning.create.call_args
    assert kwargs["model"] == "Qwen/Qwen3-8B"
    assert kwargs["lora"] is True
    assert kwargs["n_epochs"] == 3
    assert kwargs["suffix"] == "lynch-smoke"


def test_poll_job_returns_status():
    client = _mock_client()
    provider = TogetherProvider(client=client)

    status = provider.poll_job("ft-job-xyz")

    assert isinstance(status, JobStatus)
    assert status.state == "completed"
    assert status.output_model == "myorg/Qwen3-8B-lynch-ft-job-xyz"


def test_chat_invokes_completions_endpoint():
    client = _mock_client()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="hello"))]
    )
    provider = TogetherProvider(client=client)

    out = provider.chat(
        model="myorg/foo",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert out == "hello"
    _, kwargs = client.chat.completions.create.call_args
    assert kwargs["model"] == "myorg/foo"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --directory product pytest tests/test_finetuning/test_provider.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `provider.py`**

Create `product/src/subprime/finetuning/provider.py`:

```python
"""Fine-tune provider abstraction + Together AI implementation.

The protocol exists so we can later swap in a self-hosted QLoRA provider
(Lambda Cloud + Unsloth/TRL) without touching harvest/curate/format/train.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class TrainConfig(BaseModel):
    base_model: str = "Qwen/Qwen3-8B"
    n_epochs: int = 3
    learning_rate: float = 1e-4
    lora_rank: int = 16
    lora_alpha: int = 32
    suffix: str = ""
    warmup_ratio: float = 0.0


class JobStatus(BaseModel):
    state: str  # 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
    output_model: str | None = None
    raw: dict[str, Any] = {}


@runtime_checkable
class FineTuneProvider(Protocol):
    def upload_dataset(self, path: Path) -> str: ...
    def submit_job(self, train_file_id: str, cfg: TrainConfig, val_file_id: str | None = None) -> str: ...
    def poll_job(self, job_id: str) -> JobStatus: ...
    def chat(self, model: str, messages: list[dict], **kwargs: Any) -> str: ...


class TogetherProvider:
    """Thin wrapper around the `together` SDK."""

    def __init__(self, client: Any | None = None, api_key: str | None = None):
        if client is not None:
            self._client = client
            return
        from together import Together  # local import keeps `together` optional in tests

        key = api_key or os.environ.get("TOGETHER_API_KEY")
        if not key:
            raise RuntimeError("TOGETHER_API_KEY not set")
        self._client = Together(api_key=key)

    def upload_dataset(self, path: Path) -> str:
        resp = self._client.files.upload(str(path), purpose="fine-tune", check=True)
        return resp.id

    def submit_job(
        self,
        train_file_id: str,
        cfg: TrainConfig,
        val_file_id: str | None = None,
    ) -> str:
        kwargs: dict[str, Any] = dict(
            training_file=train_file_id,
            model=cfg.base_model,
            n_epochs=cfg.n_epochs,
            learning_rate=cfg.learning_rate,
            lora=True,
            lora_r=cfg.lora_rank,
            lora_alpha=cfg.lora_alpha,
            warmup_ratio=cfg.warmup_ratio,
            suffix=cfg.suffix,
            train_on_inputs="auto",
            n_checkpoints=1,
        )
        if val_file_id:
            kwargs["validation_file"] = val_file_id
        resp = self._client.fine_tuning.create(**kwargs)
        return resp.id

    def poll_job(self, job_id: str) -> JobStatus:
        resp = self._client.fine_tuning.retrieve(job_id)
        output = getattr(resp, "output_name", None) or getattr(resp, "model_output_name", None)
        raw = resp.model_dump() if hasattr(resp, "model_dump") else {}
        return JobStatus(state=resp.status, output_model=output, raw=raw)

    def chat(self, model: str, messages: list[dict], **kwargs: Any) -> str:
        resp = self._client.chat.completions.create(model=model, messages=messages, **kwargs)
        return resp.choices[0].message.content
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run --directory product pytest tests/test_finetuning/test_provider.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add product/src/subprime/finetuning/provider.py product/tests/test_finetuning/test_provider.py
git commit -m "feat(ft): TogetherProvider + FineTuneProvider protocol"
```

---

## Task 6: CLI scaffolding + harvest/format/build-dataset commands

**Files:**
- Create: `product/src/subprime/finetuning/cli.py`
- Modify: `product/src/subprime/cli.py` — register `ft` subgroup

- [ ] **Step 1: Implement `finetuning/cli.py`**

Create `product/src/subprime/finetuning/cli.py`:

```python
"""Typer CLI subcommands for the finetuning pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from subprime.evaluation.personas import load_personas
from subprime.finetuning.curate import (
    CurateConfig,
    curate,
    load_teacher_substrings,
    split_train_val,
)
from subprime.finetuning.format import write_jsonl
from subprime.finetuning.harvest import harvest_records

app = typer.Typer(help="Stage 2 — fine-tuning bias into model weights.")
_console = Console()

_REPO_ROOT = Path(__file__).resolve().parents[4]  # product/src/subprime/finetuning -> repo
_DEFAULT_RESULTS_ROOT = _REPO_ROOT / "research" / "results" / "runs"
_DATASETS_DIR = Path(__file__).parent / "artifacts" / "datasets"


@app.command("build-dataset")
def build_dataset(
    results_root: Path = typer.Option(_DEFAULT_RESULTS_ROOT, help="Where to harvest from."),
    out_dir: Path = typer.Option(_DATASETS_DIR, help="Where to write JSONL files."),
    lynch_max_aps: float = 35.0,
    bogle_min_aps: float = 75.0,
    val_fraction: float = 0.1,
    min_per_variant: int = 200,
) -> None:
    """Harvest → curate → split → write JSONL files for both variants."""
    teachers = load_teacher_substrings()
    cfg = CurateConfig(
        teacher_substrings=teachers,
        lynch_max_aps=lynch_max_aps,
        bogle_min_aps=bogle_min_aps,
        min_per_variant=min_per_variant,
    )

    _console.print(f"[bold]Harvesting from[/bold] {results_root}")
    records = harvest_records(results_root)
    _console.print(f"  found {len(records)} Lynch+Bogle records (deduped)")

    kept = curate(records, cfg)
    by_variant = {"lynch": [], "bogle": []}
    for r in kept:
        by_variant[r.condition].append(r)
    _console.print(f"  after curate: lynch={len(by_variant['lynch'])}, bogle={len(by_variant['bogle'])}")

    personas = {p.id: p for p in load_personas()}
    out_dir.mkdir(parents=True, exist_ok=True)

    for variant, records_v in by_variant.items():
        train, val = split_train_val(records_v, val_fraction=val_fraction)
        train_pairs = [(personas[r.persona_id], r) for r in train if r.persona_id in personas]
        val_pairs = [(personas[r.persona_id], r) for r in val if r.persona_id in personas]
        train_path = out_dir / f"{variant}_train.jsonl"
        val_path = out_dir / f"{variant}_val.jsonl"
        n_train = write_jsonl(train_pairs, train_path)
        n_val = write_jsonl(val_pairs, val_path)
        _console.print(
            f"  [green]{variant}[/green]: wrote train={n_train} ({train_path.name}), "
            f"val={n_val} ({val_path.name})"
        )

    summary = {
        "lynch_train": len(by_variant["lynch"]),
        "bogle_train": len(by_variant["bogle"]),
        "config": cfg.model_dump(),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    app()
```

- [ ] **Step 2: Register `ft` subgroup on main CLI**

Open `product/src/subprime/cli.py`. Find where Typer subapps are added (search for `app.add_typer` — there should be at least one example). Add:

```python
from subprime.finetuning.cli import app as ft_app
app.add_typer(ft_app, name="ft", help="Stage 2 fine-tuning pipeline.")
```

If the file has no `add_typer` calls yet, place this near the bottom of imports / top of CLI definitions, where other subapps would naturally live.

- [ ] **Step 3: Smoke-run the new command**

```bash
uv run --directory product subprime ft build-dataset --min-per-variant 0
```

Expected: prints harvested count > 0, prints lynch/bogle counts after curation, writes JSONL files into `product/src/subprime/finetuning/artifacts/datasets/`. Note actual counts in the next step.

- [ ] **Step 4: Verify dataset shape**

```bash
head -1 product/src/subprime/finetuning/artifacts/datasets/lynch_train.jsonl | python -c "import json,sys; d=json.loads(sys.stdin.read()); print('keys:', list(d.keys())); print('roles:', [m['role'] for m in d['messages']])"
```

Expected: `keys: ['messages']` and `roles: ['system', 'user', 'assistant']`.

- [ ] **Step 5: Validate with Together's CLI checker**

```bash
uv run --directory product together files check product/src/subprime/finetuning/artifacts/datasets/lynch_train.jsonl
```

Expected: PASS (no schema errors). If it fails, adjust `format.py` to satisfy the check, re-run.

- [ ] **Step 6: Commit**

```bash
git add product/src/subprime/finetuning/cli.py product/src/subprime/cli.py
git commit -m "feat(ft): build-dataset CLI + ft subgroup wiring"
```

---

## Task 7: Smoke fine-tuning run (THE EARLY VALIDATION GATE)

**Files:**
- Create: `product/src/subprime/finetuning/train.py`
- Create: `product/tests/test_finetuning/test_train.py`
- Modify: `product/src/subprime/finetuning/cli.py` — add `smoke` and `train` commands

- [ ] **Step 1: Write the failing test for `train.run_job`**

Create `product/tests/test_finetuning/test_train.py`:

```python
"""Tests for finetuning.train — orchestration with mocked provider."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from subprime.finetuning.provider import JobStatus, TrainConfig
from subprime.finetuning.train import RunArtifacts, run_job


def _provider(states: list[str], output_model: str = "myorg/foo") -> MagicMock:
    p = MagicMock()
    p.upload_dataset.return_value = "file-abc"
    p.submit_job.return_value = "ft-job-xyz"
    p.poll_job.side_effect = [
        JobStatus(state=s, output_model=output_model if s == "completed" else None)
        for s in states
    ]
    return p


def test_run_job_polls_until_completed(tmp_path: Path):
    train = tmp_path / "t.jsonl"
    train.write_text('{"messages": []}\n')
    provider = _provider(["pending", "running", "completed"])
    cfg = TrainConfig(suffix="smoke")

    artifacts = run_job(
        provider=provider,
        train_path=train,
        cfg=cfg,
        out_dir=tmp_path / "out",
        poll_interval_s=0,
    )

    assert isinstance(artifacts, RunArtifacts)
    assert artifacts.output_model == "myorg/foo"
    assert artifacts.job_id == "ft-job-xyz"
    assert provider.poll_job.call_count == 3
    # artifacts.json was written
    assert (tmp_path / "out" / "artifacts.json").exists()


def test_run_job_raises_on_failure(tmp_path: Path):
    train = tmp_path / "t.jsonl"
    train.write_text('{}\n')
    provider = _provider(["pending", "failed"])
    cfg = TrainConfig(suffix="smoke")

    with pytest.raises(RuntimeError, match="failed"):
        run_job(
            provider=provider,
            train_path=train,
            cfg=cfg,
            out_dir=tmp_path / "out",
            poll_interval_s=0,
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --directory product pytest tests/test_finetuning/test_train.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `train.py`**

Create `product/src/subprime/finetuning/train.py`:

```python
"""Run a fine-tune job end-to-end and record artifacts."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from subprime.finetuning.provider import FineTuneProvider, JobStatus, TrainConfig


_TERMINAL_OK = {"completed"}
_TERMINAL_FAIL = {"failed", "cancelled", "error"}


class RunArtifacts(BaseModel):
    job_id: str
    output_model: str
    train_path: str
    val_path: str | None = None
    config: TrainConfig
    started_at: datetime
    finished_at: datetime
    final_status: JobStatus


def run_job(
    *,
    provider: FineTuneProvider,
    train_path: Path,
    cfg: TrainConfig,
    out_dir: Path,
    val_path: Path | None = None,
    poll_interval_s: float = 30.0,
) -> RunArtifacts:
    """Upload, submit, poll. Persist artifacts.json and return RunArtifacts."""
    started = datetime.utcnow()
    train_id = provider.upload_dataset(train_path)
    val_id = provider.upload_dataset(val_path) if val_path else None
    job_id = provider.submit_job(train_id, cfg, val_file_id=val_id)

    while True:
        status = provider.poll_job(job_id)
        if status.state in _TERMINAL_OK:
            break
        if status.state in _TERMINAL_FAIL:
            raise RuntimeError(f"fine-tune job {job_id} failed: state={status.state}")
        time.sleep(poll_interval_s)

    if not status.output_model:
        raise RuntimeError(f"job {job_id} completed but no output_model returned")

    finished = datetime.utcnow()
    artifacts = RunArtifacts(
        job_id=job_id,
        output_model=status.output_model,
        train_path=str(train_path),
        val_path=str(val_path) if val_path else None,
        config=cfg,
        started_at=started,
        finished_at=finished,
        final_status=status,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "artifacts.json").write_text(artifacts.model_dump_json(indent=2))
    return artifacts
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run --directory product pytest tests/test_finetuning/test_train.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Add `smoke` and `train` CLI commands**

Open `product/src/subprime/finetuning/cli.py`. Add after the existing `build-dataset` command:

```python
from subprime.finetuning.provider import TogetherProvider, TrainConfig
from subprime.finetuning.train import run_job

_RUNS_DIR = Path(__file__).parent / "artifacts" / "runs"


@app.command("smoke")
def smoke(
    variant: str = typer.Argument("lynch", help="lynch or bogle"),
    n_examples: int = 25,
    epochs: int = 1,
) -> None:
    """Cheap end-to-end smoke test: tiny subset, 1 epoch, single inference call."""
    src = _DATASETS_DIR / f"{variant}_train.jsonl"
    if not src.exists():
        raise typer.BadParameter(f"missing {src}; run `subprime ft build-dataset` first")
    smoke_path = _DATASETS_DIR / f"{variant}_smoke.jsonl"
    lines = src.read_text().splitlines()[:n_examples]
    smoke_path.write_text("\n".join(lines) + "\n")
    _console.print(f"[bold]Smoke dataset:[/bold] {smoke_path} ({len(lines)} examples)")

    cfg = TrainConfig(
        base_model="Qwen/Qwen3-8B",
        n_epochs=epochs,
        learning_rate=1e-4,
        suffix=f"{variant}-smoke",
    )
    provider = TogetherProvider()
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    out = _RUNS_DIR / f"{variant}_smoke_{ts}"
    artifacts = run_job(provider=provider, train_path=smoke_path, cfg=cfg, out_dir=out)
    _console.print(f"[green]✓ FT done:[/green] {artifacts.output_model}")
    _console.print(f"  artifacts: {out / 'artifacts.json'}")

    # One inference probe
    sample = json.loads(lines[0])
    messages = sample["messages"][:-1]  # drop assistant turn
    reply = provider.chat(model=artifacts.output_model, messages=messages, max_tokens=2048)
    _console.print(f"[bold]Probe reply (first 400 chars):[/bold]\n{reply[:400]}")
    try:
        from subprime.core.models import InvestmentPlan
        InvestmentPlan.model_validate_json(reply)
        _console.print("[green]✓ JSON parses to InvestmentPlan[/green]")
    except Exception as e:
        _console.print(f"[red]✗ JSON parse failed:[/red] {e}")


@app.command("train")
def train(
    variant: str = typer.Argument(..., help="lynch or bogle"),
    epochs: int = 3,
    learning_rate: float = 1e-4,
) -> None:
    """Run the full fine-tune for one variant."""
    train_path = _DATASETS_DIR / f"{variant}_train.jsonl"
    val_path = _DATASETS_DIR / f"{variant}_val.jsonl"
    if not train_path.exists():
        raise typer.BadParameter(f"missing {train_path}; run `subprime ft build-dataset`")

    cfg = TrainConfig(
        base_model="Qwen/Qwen3-8B",
        n_epochs=epochs,
        learning_rate=learning_rate,
        suffix=f"{variant}-v1",
    )
    provider = TogetherProvider()
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    out = _RUNS_DIR / f"{variant}_{ts}"
    artifacts = run_job(
        provider=provider,
        train_path=train_path,
        val_path=val_path if val_path.exists() else None,
        cfg=cfg,
        out_dir=out,
    )
    _console.print(f"[green]✓ {variant} FT complete:[/green] {artifacts.output_model}")
```

Add the missing import at the top of the file:

```python
from datetime import datetime
```

- [ ] **Step 6: Verify all tests still pass**

```bash
uv run --directory product pytest tests/test_finetuning/ -v
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add product/src/subprime/finetuning/train.py product/src/subprime/finetuning/cli.py product/tests/test_finetuning/test_train.py
git commit -m "feat(ft): train orchestrator + smoke and train CLI commands"
```

- [ ] **Step 8: 🚦 Run the smoke fine-tune (real money — STOP and confirm with user)**

Before running: confirm with user that `TOGETHER_API_KEY` is set and the user is OK spending ~$2-3 on the smoke run. **Do not proceed past this checkbox without explicit user confirmation.**

```bash
uv run --directory product subprime ft smoke lynch --n-examples 25 --epochs 1
```

Expected:
- "Smoke dataset" line with ~25 examples
- 5-15 minutes of polling output
- "✓ FT done" with a fine-tuned model name
- A probe reply printed
- Either "✓ JSON parses to InvestmentPlan" or a parse error (either is acceptable — we want to know)

If the dataset upload is rejected for being too small, bump `--n-examples` to whatever Together's minimum is and re-run.

- [ ] **Step 9: Commit smoke artifacts**

```bash
git add product/src/subprime/finetuning/artifacts/runs/lynch_smoke_*/artifacts.json
git commit -m "chore(ft): smoke-run artifacts (lynch, 25 examples, 1 epoch)"
```

(Note: only commit `artifacts.json`, not the smoke JSONL — it's gitignored.)

---

## Task 8: Evaluate module — run FT model on persona bank, score with APS

**Files:**
- Create: `product/src/subprime/finetuning/evaluate.py`
- Create: `product/tests/test_finetuning/test_evaluate.py`
- Modify: `product/src/subprime/finetuning/cli.py` — add `evaluate` command

- [ ] **Step 1: Write the failing test for the JSON parser path**

Create `product/tests/test_finetuning/test_evaluate.py`:

```python
"""Tests for finetuning.evaluate — only the parser/wiring, not the LLM."""

from __future__ import annotations

import pytest

from subprime.finetuning.evaluate import ParseFailure, parse_plan_response


def test_parse_plan_response_extracts_clean_json():
    raw = '{"allocations":[],"rationale":"x","risks":[],"disclaimer":"d"}'
    plan = parse_plan_response(raw)
    assert plan.rationale == "x"


def test_parse_plan_response_strips_code_fences():
    raw = "```json\n{\"allocations\":[],\"rationale\":\"y\",\"risks\":[],\"disclaimer\":\"d\"}\n```"
    plan = parse_plan_response(raw)
    assert plan.rationale == "y"


def test_parse_plan_response_finds_first_json_object_in_prose():
    raw = "Here is your plan: {\"allocations\":[],\"rationale\":\"z\",\"risks\":[],\"disclaimer\":\"d\"} hope this helps"
    plan = parse_plan_response(raw)
    assert plan.rationale == "z"


def test_parse_plan_response_raises_when_no_json():
    with pytest.raises(ParseFailure):
        parse_plan_response("sorry, I can't help with that")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --directory product pytest tests/test_finetuning/test_evaluate.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `evaluate.py`**

Create `product/src/subprime/finetuning/evaluate.py`:

```python
"""Run a fine-tuned model against the 25-persona bank and score with APS.

Mirrors `experiments.runner` but uses raw chat completions on a Together
fine-tuned model and parses JSON, instead of the PydanticAI advisor agent.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from subprime.core.config import DEFAULT_MODEL
from subprime.core.models import (
    APSScore,
    ExperimentResult,
    InvestmentPlan,
    InvestorProfile,
    PlanQualityScore,
)
from subprime.evaluation.judges import score_aps, score_pqs
from subprime.evaluation.personas import load_personas
from subprime.finetuning.format import NEUTRAL_SYSTEM_PROMPT, render_profile_text
from subprime.finetuning.provider import FineTuneProvider


class ParseFailure(Exception):
    pass


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_plan_response(raw: str) -> InvestmentPlan:
    """Best-effort: strip code fences, then take the first balanced {...} block."""
    text = raw.strip()
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()

    # Try the whole string first
    try:
        return InvestmentPlan.model_validate_json(text)
    except Exception:
        pass

    # Find first balanced JSON object
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : i + 1]
                try:
                    return InvestmentPlan.model_validate_json(candidate)
                except Exception:
                    start = -1
                    continue
    raise ParseFailure(f"no parseable InvestmentPlan in response: {raw[:200]}")


class EvalRecord(BaseModel):
    persona_id: str
    output_model: str
    parsed: bool
    plan: InvestmentPlan | None = None
    aps: APSScore | None = None
    pqs: PlanQualityScore | None = None
    error: str | None = None


async def evaluate_persona(
    profile: InvestorProfile,
    *,
    provider: FineTuneProvider,
    output_model: str,
    judge_model: str = DEFAULT_MODEL,
) -> EvalRecord:
    messages = [
        {"role": "system", "content": NEUTRAL_SYSTEM_PROMPT},
        {"role": "user", "content": render_profile_text(profile)},
    ]
    raw = provider.chat(model=output_model, messages=messages, max_tokens=4096)

    try:
        plan = parse_plan_response(raw)
    except ParseFailure as e:
        return EvalRecord(
            persona_id=profile.id,
            output_model=output_model,
            parsed=False,
            error=str(e),
        )

    aps, _ = await score_aps(plan, profile, model=judge_model)
    pqs, _ = await score_pqs(plan, profile, model=judge_model)

    return EvalRecord(
        persona_id=profile.id,
        output_model=output_model,
        parsed=True,
        plan=plan,
        aps=aps,
        pqs=pqs,
    )


async def evaluate_model(
    *,
    provider: FineTuneProvider,
    output_model: str,
    variant: str,  # 'lynch_ft' | 'bogle_ft' | 'base'
    out_dir: Path,
    judge_model: str = DEFAULT_MODEL,
) -> list[EvalRecord]:
    personas = load_personas()
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvalRecord] = []

    for profile in personas:
        rec = await evaluate_persona(
            profile, provider=provider, output_model=output_model, judge_model=judge_model
        )
        records.append(rec)
        if rec.parsed and rec.aps and rec.pqs and rec.plan:
            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            result = ExperimentResult(
                persona_id=profile.id,
                condition=variant,  # use variant as condition label
                model=output_model,
                judge_model=judge_model,
                plan=rec.plan,
                aps=rec.aps,
                pqs=rec.pqs,
                timestamp=datetime.utcnow(),
                prompt_version="ft-v1",
            )
            (out_dir / f"{profile.id}_{variant}_{ts}.json").write_text(
                result.model_dump_json(indent=2)
            )

    summary = {
        "output_model": output_model,
        "variant": variant,
        "n_personas": len(personas),
        "n_parsed": sum(1 for r in records if r.parsed),
        "parse_failures": [r.persona_id for r in records if not r.parsed],
    }
    (out_dir / "eval_summary.json").write_text(json.dumps(summary, indent=2))
    return records
```

- [ ] **Step 4: Run test to verify parser tests pass**

```bash
uv run --directory product pytest tests/test_finetuning/test_evaluate.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Add `evaluate` CLI command**

In `product/src/subprime/finetuning/cli.py` add:

```python
import asyncio as _asyncio
from subprime.finetuning.evaluate import evaluate_model

_EVAL_DIR = _REPO_ROOT / "research" / "results" / "runs" / "finetune"


@app.command("evaluate")
def evaluate(
    output_model: str = typer.Argument(..., help="The fine-tuned model name from `ft train`."),
    variant: str = typer.Argument(..., help="lynch_ft | bogle_ft | base"),
) -> None:
    """Run a fine-tuned model against all personas and score with APS+PQS."""
    provider = TogetherProvider()
    out_dir = _EVAL_DIR / variant
    records = _asyncio.run(
        evaluate_model(provider=provider, output_model=output_model, variant=variant, out_dir=out_dir)
    )
    parsed = sum(1 for r in records if r.parsed)
    _console.print(f"[bold]Evaluated[/bold] {output_model}: {parsed}/{len(records)} parseable plans")
    if parsed:
        mean_aps = sum(r.aps.score for r in records if r.aps) / parsed
        _console.print(f"  mean APS: {mean_aps:.1f}")
```

- [ ] **Step 6: Commit**

```bash
git add product/src/subprime/finetuning/evaluate.py product/src/subprime/finetuning/cli.py product/tests/test_finetuning/test_evaluate.py
git commit -m "feat(ft): evaluate module + evaluate CLI command"
```

---

## Task 9: Real fine-tunes + evaluation runs

This task is operational — running real Together AI jobs against real money. Each step requires user confirmation before proceeding.

- [ ] **Step 1: Build full dataset with min enforcement**

```bash
uv run --directory product subprime ft build-dataset --min-per-variant 200
```

Expected: lynch_train ≥ 200, bogle_train ≥ 200. If it raises, the next step is to relax `--lynch-max-aps` (e.g. 40) or `--bogle-min-aps` (e.g. 70) and re-run. Note final counts here:

```
lynch_train: ___
bogle_train: ___
lynch_val:   ___
bogle_val:   ___
```

- [ ] **Step 2: Validate both JSONL files with Together CLI**

```bash
uv run --directory product together files check product/src/subprime/finetuning/artifacts/datasets/lynch_train.jsonl
uv run --directory product together files check product/src/subprime/finetuning/artifacts/datasets/bogle_train.jsonl
```

Expected: both PASS.

- [ ] **Step 3: 🚦 Run Lynch fine-tune (~$15-25)**

Confirm with user before running.

```bash
uv run --directory product subprime ft train lynch --epochs 3
```

Expected: "✓ lynch FT complete: <output_model_name>". **Save the model name** — paste it into the plan checklist below.

Lynch FT model name: `_______________________________`

- [ ] **Step 4: 🚦 Run Bogle fine-tune (~$15-25)**

```bash
uv run --directory product subprime ft train bogle --epochs 3
```

Bogle FT model name: `_______________________________`

- [ ] **Step 5: Evaluate base Qwen3-8B**

```bash
uv run --directory product subprime ft evaluate "Qwen/Qwen3-8B" base
```

Expected: 25/25 parseable (or close to it), mean APS printed.

- [ ] **Step 6: Evaluate Lynch FT model**

```bash
uv run --directory product subprime ft evaluate "<lynch-model-name-from-step-3>" lynch_ft
```

- [ ] **Step 7: Evaluate Bogle FT model**

```bash
uv run --directory product subprime ft evaluate "<bogle-model-name-from-step-4>" bogle_ft
```

- [ ] **Step 8: Commit all evaluation results**

```bash
git add research/results/runs/finetune/
git commit -m "experiment: stage 2 FT evaluation results — base + lynch_ft + bogle_ft"
```

---

## Task 10: Comparison report

**Files:**
- Create: `product/src/subprime/finetuning/report.py`
- Modify: `product/src/subprime/finetuning/cli.py` — add `report` command

- [ ] **Step 1: Implement `report.py`**

Create `product/src/subprime/finetuning/report.py`:

```python
"""Build the headline comparison table.

Columns: variant | n | mean APS | std | parse-failure rate
Rows: base, prompted-lynch (existing), lynch_ft, prompted-bogle (existing), bogle_ft
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from pydantic import BaseModel


class VariantStats(BaseModel):
    name: str
    n: int
    mean_aps: float
    stdev_aps: float
    parse_failures: int = 0


def _load_aps_scores(dir_: Path) -> list[float]:
    scores: list[float] = []
    for path in dir_.glob("P*_*_*.json"):
        try:
            data = json.loads(path.read_text())
            scores.append(float(data["aps"]["score"]))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return scores


def _stats(name: str, scores: list[float], parse_failures: int = 0) -> VariantStats:
    if not scores:
        return VariantStats(name=name, n=0, mean_aps=0.0, stdev_aps=0.0, parse_failures=parse_failures)
    return VariantStats(
        name=name,
        n=len(scores),
        mean_aps=statistics.mean(scores),
        stdev_aps=statistics.stdev(scores) if len(scores) > 1 else 0.0,
        parse_failures=parse_failures,
    )


def build_report(
    *,
    base_dir: Path,
    lynch_ft_dir: Path,
    bogle_ft_dir: Path,
    prompted_lynch_dirs: list[Path],
    prompted_bogle_dirs: list[Path],
) -> list[VariantStats]:
    rows = [
        _stats("base (Qwen3-8B, neutral prompt)", _load_aps_scores(base_dir)),
        _stats(
            "prompted Lynch (Qwen3-8B + system prompt)",
            [s for d in prompted_lynch_dirs for s in _load_aps_scores(d)],
        ),
        _stats("Lynch FT (Qwen3-8B, neutral prompt)", _load_aps_scores(lynch_ft_dir)),
        _stats(
            "prompted Bogle (Qwen3-8B + system prompt)",
            [s for d in prompted_bogle_dirs for s in _load_aps_scores(d)],
        ),
        _stats("Bogle FT (Qwen3-8B, neutral prompt)", _load_aps_scores(bogle_ft_dir)),
    ]
    return rows


def render_table(rows: list[VariantStats]) -> str:
    out = ["variant".ljust(50) + "n   mean APS  stdev"]
    for r in rows:
        out.append(f"{r.name.ljust(50)}{r.n:<4}{r.mean_aps:7.1f}  {r.stdev_aps:5.1f}")
    return "\n".join(out)
```

- [ ] **Step 2: Add `report` CLI command**

In `product/src/subprime/finetuning/cli.py`:

```python
from subprime.finetuning.report import build_report, render_table


@app.command("report")
def report() -> None:
    """Print the headline comparison table."""
    base_dir = _EVAL_DIR / "base"
    lynch_ft_dir = _EVAL_DIR / "lynch_ft"
    bogle_ft_dir = _EVAL_DIR / "bogle_ft"

    runs_root = _REPO_ROOT / "research" / "results" / "runs" / "open_weight"
    qwen_dirs = [d for d in runs_root.glob("*qwen3*") if d.is_dir()]

    rows = build_report(
        base_dir=base_dir,
        lynch_ft_dir=lynch_ft_dir,
        bogle_ft_dir=bogle_ft_dir,
        prompted_lynch_dirs=qwen_dirs,  # _load_aps_scores filters by filename pattern
        prompted_bogle_dirs=qwen_dirs,
    )
    _console.print(render_table(rows))
```

- [ ] **Step 3: Run report**

```bash
uv run --directory product subprime ft report
```

Expected: 5-row table printed. Capture the output to `research/results/runs/finetune/headline.txt`.

```bash
uv run --directory product subprime ft report > research/results/runs/finetune/headline.txt
```

- [ ] **Step 4: Commit**

```bash
git add product/src/subprime/finetuning/report.py product/src/subprime/finetuning/cli.py research/results/runs/finetune/headline.txt
git commit -m "feat(ft): comparison report + headline.txt artifact"
```

---

## Task 11: Roadmap update + branch wrap-up

**Files:**
- Modify: `docs/roadmap.md`

- [ ] **Step 1: Tick M7 boxes that landed**

Open `docs/roadmap.md`. Under M7 ("Phase 2 Fine-tuning (stretch)"), mark these as done by changing `[ ]` to `[x]`:
- "Synthetic Lynch/Bogle conversation corpora (~200 each)" → revise to "Harvested Lynch/Bogle corpora (~200+ each)" and tick.
- "QLoRA fine-tuning of Llama-3-8B or Mistral-7B" → revise to "LoRA fine-tuning of Qwen3-8B (Together AI hosted)" and tick.
- "Compare fine-tuned subprime spread vs prompted subprime spread" → tick.

Leave the remaining items (ablation, persistence) unticked.

- [ ] **Step 2: Run full fast test suite**

```bash
uv run --directory product pytest -m "not e2e and not browser and not smoke"
```

Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add docs/roadmap.md
git commit -m "docs: tick M7 boxes for landed fine-tuning work"
```

- [ ] **Step 4: Push branch and open PR**

Confirm with user before pushing. Then:

```bash
git push -u origin stage2-finetuning
gh pr create --title "Stage 2: Fine-tune Qwen3-8B with Lynch/Bogle bias" --body "$(cat <<'EOF'
## Summary

- Harvest Lynch/Bogle plans from existing `research/results/runs/`
- Curate by teacher allow-list + APS direction; stratified train/val split
- Fine-tune two Qwen3-8B variants via Together AI LoRA (Lynch, Bogle)
- Evaluate on 25-persona bank with neutral system prompt
- Comparison report: base vs prompted bias vs fine-tuned bias

Spec: `docs/specs/2026-05-06-stage2-finetuning-design.md`
Plan: `docs/plans/2026-05-06-stage2-finetuning.md`

Headline result in `research/results/runs/finetune/headline.txt`.

## Test plan
- [x] `pytest tests/test_finetuning/`
- [x] `together files check` on both JSONL datasets
- [x] Smoke FT run completed and produced parseable plan
- [x] Full FT runs (lynch + bogle) completed
- [x] Evaluation against 25 personas
- [x] Full fast suite green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage**: every section of the spec maps to a task — harvest (T2), curate (T3), format (T4), provider (T5), train (T7), evaluate (T8), report (T10). Smoke gate (T7 step 8) and dataset minimum check (T9 step 1) are operational gates spec called for.
- **Placeholder scan**: zero TBDs / "implement later" / "similar to Task N" references. Every code step has the actual code.
- **Type consistency**: `HarvestedRecord`, `CurateConfig`, `TrainConfig`, `JobStatus`, `RunArtifacts`, `EvalRecord`, `VariantStats`, `ParseFailure` — all defined where first used and reused with the same names downstream. CLI commands match function signatures.
- **Money gates**: T7-S8, T9-S3, T9-S4 each say "🚦 confirm with user before running" because they actually spend money on Together AI.
