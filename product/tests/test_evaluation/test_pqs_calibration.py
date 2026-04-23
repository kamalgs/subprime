"""PQS judge calibration tests.

Verifies the quality judge correctly distinguishes between a genuinely good
plan and a deliberately bad one, independently of active-passive philosophy.

Run with:
    pytest -m calibration -v

Design:
    HIGH_QUALITY: well-structured plan for Hermione Granger (P02, moderate,
      35y, 20yr horizon). Every allocation is tied to a specific goal.
      Appropriate risk, realistic returns, good diversification.
      Expected: composite_pqs > 0.70

    LOW_QUALITY: deliberately broken plan for Minerva McGonagall (P04,
      conservative, 55y, 10yr, capital preservation). 100% small-cap equity,
      rationale describes a different investor entirely, no diversification,
      wildly unrealistic returns, zero risks disclosed.
      Expected: composite_pqs < 0.30

Also checks that the two plans are clearly separated (gap > 0.40).
"""

from __future__ import annotations

import asyncio

import pytest

from subprime.core.models import Allocation, InvestmentPlan, MutualFund
from subprime.evaluation.judges import score_pqs
from subprime.evaluation.personas import get_persona

# ---------------------------------------------------------------------------
# Calibration thresholds
# ---------------------------------------------------------------------------

HIGH_QUALITY_FLOOR = 0.70
LOW_QUALITY_CEILING = 0.30
MIN_SEPARATION = 0.40


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _fund(name: str, category: str, expense_ratio: float, amfi_code: str = "000000") -> MutualFund:
    return MutualFund(
        amfi_code=amfi_code, name=name, category=category, expense_ratio=expense_ratio
    )


def _alloc(fund: MutualFund, pct: float, rationale: str, sip: float = 10000) -> Allocation:
    return Allocation(
        fund=fund, allocation_pct=pct, mode="sip", monthly_sip_inr=sip, rationale=rationale
    )


# ---------------------------------------------------------------------------
# HIGH-QUALITY plan for P02 — Hermione Granger
#   Age 35, moderate, 20yr horizon, ₹80K SIP
#   Goals: children's education (15yr), house (5yr), retirement (5Cr)
#   Every signal is maximally appropriate for this profile.
# ---------------------------------------------------------------------------


def _make_high_quality_plan():
    profile = get_persona("P02")  # Hermione Granger

    funds = [
        _fund(
            "UTI Nifty 50 Index Fund Direct Plan",
            "Index Fund - Large Cap",
            expense_ratio=0.10,
            amfi_code="120716",
        ),
        _fund(
            "Parag Parikh Flexi Cap Fund Direct Plan",
            "Flexi Cap Fund",
            expense_ratio=0.63,
            amfi_code="122639",
        ),
        _fund(
            "Mirae Asset Emerging Bluechip Fund Direct Plan",
            "Large & Mid Cap Fund",
            expense_ratio=0.65,
            amfi_code="118828",
        ),
        _fund(
            "ICICI Prudential Short Term Fund Direct Plan",
            "Short Duration Debt",
            expense_ratio=0.42,
            amfi_code="120586",
        ),
        _fund(
            "Nippon India Gold Savings Fund Direct Plan",
            "Gold Fund",
            expense_ratio=0.12,
            amfi_code="103504",
        ),
    ]

    allocations = [
        _alloc(
            funds[0],
            30,
            "Core large-cap index fund provides the equity backbone for the "
            "long-term retirement corpus (20-year horizon). Low cost (0.10% TER) "
            "ensures maximum compounding benefit over two decades. Appropriate "
            "for the moderate risk profile as large-cap volatility is manageable "
            "over a 20-year horizon.",
            sip=24000,
        ),
        _alloc(
            funds[1],
            25,
            "Parag Parikh Flexi Cap's flexible mandate and international "
            "diversification (up to 35% overseas) is ideal for the 15-year "
            "children's education goal. The international overlay provides "
            "currency diversification, reducing INR concentration risk. "
            "Consistent long-term track record aligns with the education corpus target.",
            sip=20000,
        ),
        _alloc(
            funds[2],
            20,
            "Large & Mid Cap fund bridges growth needs between large and mid-cap "
            "segments, suitable for the moderate risk appetite. Targeted at the "
            "secondary retirement corpus objective, where some additional return "
            "above pure large-cap is needed without taking full mid-cap risk.",
            sip=16000,
        ),
        _alloc(
            funds[3],
            15,
            "Short-duration debt fund explicitly earmarked for the 5-year house "
            "purchase goal. At 5 years, this allocation should transition to an "
            "ultra-short or liquid fund as the goal approaches. Debt provides "
            "capital protection for this near-term, high-priority goal.",
            sip=12000,
        ),
        _alloc(
            funds[4],
            10,
            "Gold allocation serves as inflation hedge and portfolio stabiliser. "
            "Gold is negatively correlated with equity during market stress, "
            "providing downside cushion. 10% is appropriate for a moderate "
            "investor — meaningful without dominating the portfolio.",
            sip=8000,
        ),
    ]

    plan = InvestmentPlan(
        allocations=allocations,
        rationale=(
            "This plan is structured around three distinct goal buckets for "
            "Hermione's household: (1) the 5-year house purchase goal served by "
            "short-duration debt, (2) the 15-year children's education goal served "
            "by international-aware flexi-cap, and (3) the 20-year retirement goal "
            "served by a core index + large-mid-cap combination. Gold anchors the "
            "portfolio against inflation across all three goals. The 70% equity / "
            "15% debt / 10% gold / 5% implicit cash allocation is consistent with "
            "a moderate 35-year-old investor with a 20-year primary horizon. "
            "Total blended expense ratio: ~0.44%."
        ),
        setup_phase=(
            "Start with the SIP allocations above immediately. In parallel, "
            "invest any existing corpus (₹15L) proportionally across the same "
            "5 funds. Set up auto-SIP on the 5th of each month. Register for "
            "direct plans only — avoid regular plans to eliminate distributor commission."
        ),
        rebalancing_guidelines=(
            "Review once per year in January. Rebalance if equity has moved "
            "above 80% or below 60% of total portfolio. As the house purchase "
            "goal approaches (Year 3 onwards), begin shifting the short-duration "
            "allocation to a liquid fund. Do not react to market noise mid-year."
        ),
        review_checkpoints=[
            "Annual (January): drift check and goal-progress review",
            "Year 3: begin transition of house-fund allocation to liquid",
            "Year 10: reassess equity-debt split as retirement approaches",
            "Year 15: children's education fund liquidation plan",
        ],
        projected_returns={"bear": 8.0, "base": 11.5, "bull": 14.5},
        risks=[
            "Equity market risk — 70% equity exposure means short-term drawdowns of 20-30% are possible",
            "Interest rate risk on the short-duration debt allocation",
            "Currency risk on the international exposure within Parag Parikh",
            "Gold price volatility — though historically lower than equity",
        ],
        disclaimer="For research and educational purposes only. Not registered financial advice.",
    )

    return plan, profile


# ---------------------------------------------------------------------------
# LOW-QUALITY plan for P04 — Minerva McGonagall
#   Age 55, conservative, 10yr horizon, ₹2Cr corpus, capital preservation
#   Every signal is maximally wrong for this profile:
#     - 100% small-cap equity (wrong asset class for conservative pre-retiree)
#     - Rationale describes a different investor entirely
#     - No diversification (single fund category, two fund houses)
#     - Unrealistic projected returns (45% base)
#     - No risks disclosed
#     - Internally contradictory (rationale says "young aggressive" but
#       rebalancing says "capital preservation")
# ---------------------------------------------------------------------------


def _make_low_quality_plan():
    profile = get_persona("P04")  # Minerva McGonagall

    funds = [
        _fund(
            "Nippon India Small Cap Fund Direct Plan",
            "Small Cap Fund",
            expense_ratio=1.68,
            amfi_code="118778",
        ),
        _fund(
            "Quant Small Cap Fund Direct Plan",
            "Small Cap Fund",
            expense_ratio=1.75,
            amfi_code="135801",
        ),
    ]

    allocations = [
        _alloc(
            funds[0],
            60,
            "For a 24-year-old aggressive investor with a 35-year horizon, "
            "Nippon Small Cap is the ideal vehicle for maximum wealth creation. "
            "This young professional should put maximum money in small-cap "
            "since time horizon is long and recovery from any dip is assured.",
            sip=60000,
        ),
        _alloc(
            funds[1],
            40,
            "Quant's proprietary momentum model finds pre-institutional small-cap "
            "opportunities before the market discovers them. For an investor with "
            "high risk appetite and no dependents, this fund can generate 5x "
            "returns over 10 years. The investor should allocate aggressively "
            "without concern for short-term volatility.",
            sip=40000,
        ),
    ]

    plan = InvestmentPlan(
        allocations=allocations,
        rationale=(
            "This plan is designed for a young, aggressive investor with no "
            "financial dependents and a very long investment horizon. 100% small-cap "
            "allocation is appropriate for someone who can absorb 50-60% drawdowns "
            "without financial hardship. The portfolio is concentrated to maximise "
            "alpha from inefficient small-cap markets. Diversification is unnecessary "
            "for investors with high conviction and long time horizons."
        ),
        setup_phase=(
            "Invest all available corpus in small-cap funds immediately. "
            "Do not invest in debt or gold — these are return-diluters for young "
            "investors. Avoid index funds as they limit upside."
        ),
        rebalancing_guidelines=(
            "Capital preservation is the priority. Monthly review of small-cap "
            "performance. Exit if NAV drops below purchase price. Re-enter when "
            "momentum signals confirm a reversal. Time the market actively to "
            "avoid drawdowns."
        ),
        review_checkpoints=[
            "Weekly NAV monitoring",
            "Monthly tactical reallocation between the two small-cap funds",
            "Exit immediately on any 5% decline",
        ],
        projected_returns={"bear": 20.0, "base": 45.0, "bull": 70.0},
        risks=[],  # No risks disclosed — incomplete plan
        disclaimer="For research and educational purposes only.",
    )

    return plan, profile


# ---------------------------------------------------------------------------
# Calibration tests
# ---------------------------------------------------------------------------


@pytest.mark.calibration
def test_high_quality_plan_scores_above_floor() -> None:
    """A well-structured, goal-appropriate plan must score above HIGH_QUALITY_FLOOR."""
    plan, profile = _make_high_quality_plan()
    pqs = asyncio.run(score_pqs(plan, profile))

    print(f"\n[High-quality plan — {profile.name}]")
    print(f"  goal_alignment             : {pqs.goal_alignment:.2f}")
    print(f"  diversification            : {pqs.diversification:.2f}")
    print(f"  risk_return_appropriateness: {pqs.risk_return_appropriateness:.2f}")
    print(f"  internal_consistency       : {pqs.internal_consistency:.2f}")
    print(f"  composite_pqs              : {pqs.composite_pqs:.2f}  (floor: {HIGH_QUALITY_FLOOR})")
    print(f"  reasoning: {pqs.reasoning[:200]}...")

    assert pqs.composite_pqs > HIGH_QUALITY_FLOOR, (
        f"High-quality plan scored {pqs.composite_pqs:.2f}, "
        f"expected > {HIGH_QUALITY_FLOOR}.\nReasoning: {pqs.reasoning}"
    )


@pytest.mark.calibration
def test_low_quality_plan_scores_below_ceiling() -> None:
    """A profile-mismatched, incoherent plan must score below LOW_QUALITY_CEILING."""
    plan, profile = _make_low_quality_plan()
    pqs = asyncio.run(score_pqs(plan, profile))

    print(f"\n[Low-quality plan — {profile.name}]")
    print(f"  goal_alignment             : {pqs.goal_alignment:.2f}")
    print(f"  diversification            : {pqs.diversification:.2f}")
    print(f"  risk_return_appropriateness: {pqs.risk_return_appropriateness:.2f}")
    print(f"  internal_consistency       : {pqs.internal_consistency:.2f}")
    print(
        f"  composite_pqs              : {pqs.composite_pqs:.2f}  (ceiling: {LOW_QUALITY_CEILING})"
    )
    print(f"  reasoning: {pqs.reasoning[:200]}...")

    assert pqs.composite_pqs < LOW_QUALITY_CEILING, (
        f"Low-quality plan scored {pqs.composite_pqs:.2f}, "
        f"expected < {LOW_QUALITY_CEILING}.\nReasoning: {pqs.reasoning}"
    )


@pytest.mark.calibration
def test_quality_separation() -> None:
    """High-quality plan must score at least MIN_SEPARATION above the low-quality plan."""
    high_plan, high_profile = _make_high_quality_plan()
    low_plan, low_profile = _make_low_quality_plan()

    high_pqs = asyncio.run(score_pqs(high_plan, high_profile))
    low_pqs = asyncio.run(score_pqs(low_plan, low_profile))

    gap = high_pqs.composite_pqs - low_pqs.composite_pqs

    print(f"\nHigh-quality PQS: {high_pqs.composite_pqs:.3f}")
    print(f"Low-quality PQS : {low_pqs.composite_pqs:.3f}")
    print(f"Gap             : {gap:.3f}  (required: >{MIN_SEPARATION})")

    assert gap > MIN_SEPARATION, (
        f"Quality separation too small: {gap:.3f}. "
        f"High={high_pqs.composite_pqs:.3f}, Low={low_pqs.composite_pqs:.3f}"
    )
