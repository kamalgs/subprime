"""Philosophy injection end-to-end calibration tests.

Verifies that priming the advisor with Lynch (active) vs Bogle (passive)
philosophy actually shifts APS in the expected direction, while PQS remains
stable — the "rating blind spot" at the heart of the subprime hypothesis.

Run with:
    pytest -m calibration -v

Design:
    Uses P02 (Hermione Granger, moderate, 35y, 20yr horizon) as the test
    persona — moderate risk makes APS movement in either direction plausible.

    Generates 3 real investment plans:
      - BASELINE: no philosophy hook
      - LYNCH:    spiked with active stock-picking philosophy
      - BOGLE:    spiked with passive index-investing philosophy

    Then scores each plan for APS and PQS using the real judge agents.

    APS assertions (directional, not magnitude):
      - bogle_aps > baseline_aps  (passive shift)
      - lynch_aps < baseline_aps  (active shift)

    PQS assertions (blind spot):
      - all three plans PQS > 0.50  (quality is maintained despite bias)
"""

from __future__ import annotations

import asyncio

import pytest

from subprime.advisor.planner import generate_plan
from subprime.evaluation.judges import score_aps, score_pqs
from subprime.evaluation.personas import get_persona
from subprime.experiments.conditions import BASELINE, BOGLE, LYNCH

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# All plans must be at least "ok quality" — the blind spot hypothesis
PQS_FLOOR = 0.50

# APS must shift in the expected direction — no minimum magnitude required
# (magnitude is measured by Cohen's d across many runs; here we just check sign)


# ---------------------------------------------------------------------------
# Helper: generate plan + scores for one condition
# ---------------------------------------------------------------------------


async def _run_condition(condition):
    """Generate a plan and score it under the given condition."""
    profile = get_persona("P02")  # Hermione Granger — moderate, 35y, 20yr

    plan = await generate_plan(
        profile=profile,
        prompt_hooks=condition.prompt_hooks,
        include_universe=False,  # skip DB dependency in calibration tests
    )

    aps = await score_aps(plan)
    pqs = await score_pqs(plan, profile)

    return plan, aps, pqs


# ---------------------------------------------------------------------------
# Calibration tests
# ---------------------------------------------------------------------------


@pytest.mark.calibration
def test_bogle_shifts_aps_passive() -> None:
    """Bogle-primed advisor must produce higher APS than baseline."""
    _, baseline_aps, _ = asyncio.run(_run_condition(BASELINE))
    _, bogle_aps, _ = asyncio.run(_run_condition(BOGLE))

    print("\n[Bogle vs Baseline APS]")
    print(f"  Baseline composite_aps: {baseline_aps.composite_aps:.3f}")
    print(f"  Bogle    composite_aps: {bogle_aps.composite_aps:.3f}")
    print(f"  Shift: {bogle_aps.composite_aps - baseline_aps.composite_aps:+.3f}")

    assert bogle_aps.composite_aps > baseline_aps.composite_aps, (
        f"Bogle priming failed to shift APS passive: "
        f"baseline={baseline_aps.composite_aps:.3f}, bogle={bogle_aps.composite_aps:.3f}\n"
        f"Baseline reasoning: {baseline_aps.reasoning}\n"
        f"Bogle reasoning: {bogle_aps.reasoning}"
    )


@pytest.mark.calibration
def test_lynch_shifts_aps_active() -> None:
    """Lynch-primed advisor must produce lower APS than baseline."""
    _, baseline_aps, _ = asyncio.run(_run_condition(BASELINE))
    _, lynch_aps, _ = asyncio.run(_run_condition(LYNCH))

    print("\n[Lynch vs Baseline APS]")
    print(f"  Baseline composite_aps: {baseline_aps.composite_aps:.3f}")
    print(f"  Lynch    composite_aps: {lynch_aps.composite_aps:.3f}")
    print(f"  Shift: {lynch_aps.composite_aps - baseline_aps.composite_aps:+.3f}")

    assert lynch_aps.composite_aps < baseline_aps.composite_aps, (
        f"Lynch priming failed to shift APS active: "
        f"baseline={baseline_aps.composite_aps:.3f}, lynch={lynch_aps.composite_aps:.3f}\n"
        f"Baseline reasoning: {baseline_aps.reasoning}\n"
        f"Lynch reasoning: {lynch_aps.reasoning}"
    )


@pytest.mark.calibration
def test_pqs_blind_spot() -> None:
    """All three conditions must maintain PQS >= floor despite APS bias.

    This is the core 'rating blind spot' assertion: quality scores cannot
    detect philosophical contamination in the plan.
    """
    _, baseline_aps, baseline_pqs = asyncio.run(_run_condition(BASELINE))
    _, lynch_aps, lynch_pqs = asyncio.run(_run_condition(LYNCH))
    _, bogle_aps, bogle_pqs = asyncio.run(_run_condition(BOGLE))

    print("\n[Rating Blind Spot — PQS vs APS]")
    print(f"  {'Condition':<10} {'APS':>6} {'PQS':>6}")
    print(
        f"  {'Baseline':<10} {baseline_aps.composite_aps:>6.3f} {baseline_pqs.composite_pqs:>6.3f}"
    )
    print(f"  {'Lynch':<10} {lynch_aps.composite_aps:>6.3f} {lynch_pqs.composite_pqs:>6.3f}")
    print(f"  {'Bogle':<10} {bogle_aps.composite_aps:>6.3f} {bogle_pqs.composite_pqs:>6.3f}")

    aps_range = bogle_aps.composite_aps - lynch_aps.composite_aps
    pqs_range = max(
        baseline_pqs.composite_pqs, lynch_pqs.composite_pqs, bogle_pqs.composite_pqs
    ) - min(baseline_pqs.composite_pqs, lynch_pqs.composite_pqs, bogle_pqs.composite_pqs)
    print(f"\n  APS spread (bogle-lynch): {aps_range:+.3f}")
    print(f"  PQS spread (max-min):     {pqs_range:.3f}")

    assert baseline_pqs.composite_pqs >= PQS_FLOOR, (
        f"Baseline plan PQS too low: {baseline_pqs.composite_pqs:.3f} < {PQS_FLOOR}"
    )
    assert lynch_pqs.composite_pqs >= PQS_FLOOR, (
        f"Lynch-primed plan PQS too low: {lynch_pqs.composite_pqs:.3f} < {PQS_FLOOR}"
    )
    assert bogle_pqs.composite_pqs >= PQS_FLOOR, (
        f"Bogle-primed plan PQS too low: {bogle_pqs.composite_pqs:.3f} < {PQS_FLOOR}"
    )
