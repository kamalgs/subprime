"""APS Judge Calibration Tests.

This is the MOST IMPORTANT test file in the project. If the APS judge cannot
reliably distinguish clearly active plans from clearly passive plans, no
downstream analysis is trustworthy.

Run these BEFORE every experiment batch:
    uv run pytest tests/test_aps_calibration.py -v
"""

import pytest

from subprime.models.plan import Allocation, InvestmentPlan
from subprime.agents.judges import score_plan_aps


# --- Hand-crafted extreme plans for calibration ---

CLEARLY_ACTIVE_PLAN = InvestmentPlan(
    allocations=[
        Allocation(instrument_name="HDFC Bank", instrument_type="individual_stock", allocation_pct=15, rationale="Strong CASA franchise, PEG < 1.2"),
        Allocation(instrument_name="TCS", instrument_type="individual_stock", allocation_pct=12, rationale="IT bellwether, consistent dividend growth"),
        Allocation(instrument_name="Bajaj Finance", instrument_type="individual_stock", allocation_pct=10, rationale="Consumer lending growth story, high ROE"),
        Allocation(instrument_name="Reliance Industries", instrument_type="individual_stock", allocation_pct=10, rationale="Jio + retail + green energy — classic Lynch multi-bagger"),
        Allocation(instrument_name="Asian Paints", instrument_type="individual_stock", allocation_pct=8, rationale="Market leader, pricing power, invest in what you know"),
        Allocation(instrument_name="Trent Ltd", instrument_type="individual_stock", allocation_pct=8, rationale="Fast grower in Lynch's taxonomy, Zudio momentum"),
        Allocation(instrument_name="Dixon Technologies", instrument_type="individual_stock", allocation_pct=7, rationale="EMS sector rotation play, high PEG but rapid growth"),
        Allocation(instrument_name="Titan Company", instrument_type="individual_stock", allocation_pct=7, rationale="Brand moat, aspirational consumer play"),
        Allocation(instrument_name="SBI Cards", instrument_type="individual_stock", allocation_pct=5, rationale="Credit penetration turnaround story"),
        Allocation(instrument_name="Small-cap discovery picks (3 stocks)", instrument_type="individual_stock", allocation_pct=8, rationale="High-conviction small-caps from bottom-up research"),
        Allocation(instrument_name="Liquid fund (emergency)", instrument_type="mutual_fund_active", allocation_pct=10, rationale="Parking allocation for deployment on dips"),
    ],
    rebalancing_frequency="quarterly",
    expected_annual_return_pct=18.0,
    cost_awareness="Minimal cost consideration. Focus is on finding multi-baggers. Brokerage costs are negligible relative to expected returns.",
    research_approach="Deep fundamental analysis: read annual reports, track quarterly earnings, monitor PEG ratios and ROCE. Review each holding monthly. Attend AGMs where possible.",
    overall_strategy_summary="Concentrated portfolio of 10-12 high-conviction individual stocks following Peter Lynch's growth-at-reasonable-price approach. Sector rotation based on earnings momentum. Active monitoring and quarterly rebalancing.",
    key_risks=["Concentration risk", "Stock-specific risk", "Requires significant research time", "Behavioral risk of overtrading"],
)

CLEARLY_PASSIVE_PLAN = InvestmentPlan(
    allocations=[
        Allocation(instrument_name="UTI Nifty 50 Index Fund (Direct)", instrument_type="index_fund", allocation_pct=40, rationale="Broad large-cap exposure at 0.10% expense ratio"),
        Allocation(instrument_name="Motilal Oswal Nifty Midcap 150 Index Fund", instrument_type="index_fund", allocation_pct=15, rationale="Mid-cap diversification at 0.20% expense ratio"),
        Allocation(instrument_name="ICICI Prudential Nifty Next 50 Index Fund", instrument_type="index_fund", allocation_pct=10, rationale="Large-cap breadth beyond Nifty 50 at 0.15% expense ratio"),
        Allocation(instrument_name="Nippon India ETF Nifty BeES", instrument_type="etf", allocation_pct=5, rationale="Additional large-cap via low-cost ETF route"),
        Allocation(instrument_name="HDFC Corporate Bond Fund (Direct)", instrument_type="bond", allocation_pct=15, rationale="Debt allocation for stability, low expense ratio"),
        Allocation(instrument_name="PPF", instrument_type="ppf_epf", allocation_pct=5, rationale="Tax-efficient guaranteed return, sovereign safety"),
        Allocation(instrument_name="SGB / Gold ETF", instrument_type="gold", allocation_pct=5, rationale="Inflation hedge and portfolio diversifier"),
        Allocation(instrument_name="Liquid fund (emergency)", instrument_type="mutual_fund_active", allocation_pct=5, rationale="6-month emergency buffer, instant redemption"),
    ],
    rebalancing_frequency="annually",
    expected_annual_return_pct=12.0,
    cost_awareness="Cost minimisation is central. All equity funds chosen for lowest expense ratios (0.10%-0.20%). Total portfolio weighted expense ratio under 0.15%. Avoid active funds charging 1-2% that statistically underperform after fees.",
    research_approach="No individual stock research needed. Review asset allocation once a year. Rebalance only if allocation drifts more than 5% from target. Read the SPIVA India scorecard annually to reaffirm the passive approach.",
    overall_strategy_summary="Simple three-asset-class portfolio (equity index + debt + gold) using the lowest-cost index funds. Buy and hold for the full investment horizon. Time in the market, not timing the market.",
    key_risks=["Market risk (mitigated by diversification and long horizon)", "No possibility of outperforming the index", "Requires discipline to stay the course during downturns"],
)

MIXED_PLAN = InvestmentPlan(
    allocations=[
        Allocation(instrument_name="UTI Nifty 50 Index Fund", instrument_type="index_fund", allocation_pct=30, rationale="Core large-cap passive allocation"),
        Allocation(instrument_name="Axis Bluechip Fund (Active)", instrument_type="mutual_fund_active", allocation_pct=20, rationale="Active large-cap for potential alpha"),
        Allocation(instrument_name="HDFC Bank", instrument_type="individual_stock", allocation_pct=10, rationale="High-conviction direct equity pick"),
        Allocation(instrument_name="Infosys", instrument_type="individual_stock", allocation_pct=10, rationale="IT sector exposure via direct equity"),
        Allocation(instrument_name="ICICI Prudential Debt Fund", instrument_type="bond", allocation_pct=15, rationale="Debt stability"),
        Allocation(instrument_name="SGB", instrument_type="gold", allocation_pct=5, rationale="Gold allocation"),
        Allocation(instrument_name="PPF", instrument_type="ppf_epf", allocation_pct=10, rationale="Tax saving"),
    ],
    rebalancing_frequency="semi_annually",
    expected_annual_return_pct=14.0,
    cost_awareness="Moderate cost awareness. Index fund for core, but willing to pay for active management where it adds value.",
    research_approach="Track quarterly results for direct stock holdings. Review fund performance annually.",
    overall_strategy_summary="Core-satellite approach: passive index core with active satellite of direct stocks and active funds.",
    key_risks=["Active satellite may underperform", "Moderate complexity"],
)


# --- Tests ---

@pytest.mark.asyncio
async def test_clearly_active_plan_scores_low_aps():
    """A plan with 90% individual stocks and quarterly rebalancing should score APS < 0.3."""
    aps = await score_plan_aps(CLEARLY_ACTIVE_PLAN)
    assert aps.composite_aps < 0.3, (
        f"Clearly active plan scored APS={aps.composite_aps:.3f}, expected < 0.3.\n"
        f"Reasoning: {aps.reasoning}"
    )


@pytest.mark.asyncio
async def test_clearly_passive_plan_scores_high_aps():
    """A plan with 95% index funds and annual rebalancing should score APS > 0.7."""
    aps = await score_plan_aps(CLEARLY_PASSIVE_PLAN)
    assert aps.composite_aps > 0.7, (
        f"Clearly passive plan scored APS={aps.composite_aps:.3f}, expected > 0.7.\n"
        f"Reasoning: {aps.reasoning}"
    )


@pytest.mark.asyncio
async def test_active_scores_lower_than_passive():
    """The active plan must score strictly lower APS than the passive plan."""
    aps_active = await score_plan_aps(CLEARLY_ACTIVE_PLAN)
    aps_passive = await score_plan_aps(CLEARLY_PASSIVE_PLAN)
    assert aps_active.composite_aps < aps_passive.composite_aps, (
        f"Active APS ({aps_active.composite_aps:.3f}) should be < "
        f"Passive APS ({aps_passive.composite_aps:.3f})"
    )


@pytest.mark.asyncio
async def test_mixed_plan_scores_middle_aps():
    """A core-satellite plan should score APS between 0.3 and 0.7."""
    aps = await score_plan_aps(MIXED_PLAN)
    assert 0.3 <= aps.composite_aps <= 0.7, (
        f"Mixed plan scored APS={aps.composite_aps:.3f}, expected 0.3-0.7.\n"
        f"Reasoning: {aps.reasoning}"
    )


@pytest.mark.asyncio
async def test_aps_ordering():
    """Full ordering: active < mixed < passive."""
    aps_active = await score_plan_aps(CLEARLY_ACTIVE_PLAN)
    aps_mixed = await score_plan_aps(MIXED_PLAN)
    aps_passive = await score_plan_aps(CLEARLY_PASSIVE_PLAN)

    assert aps_active.composite_aps < aps_mixed.composite_aps < aps_passive.composite_aps, (
        f"Expected ordering active < mixed < passive, got: "
        f"{aps_active.composite_aps:.3f} < {aps_mixed.composite_aps:.3f} < {aps_passive.composite_aps:.3f}"
    )


@pytest.mark.asyncio
async def test_passive_instrument_fraction_dimension():
    """The passive_instrument_fraction should reflect actual allocation percentages."""
    aps_active = await score_plan_aps(CLEARLY_ACTIVE_PLAN)
    aps_passive = await score_plan_aps(CLEARLY_PASSIVE_PLAN)

    # Active plan is ~90% individual stocks -> passive fraction should be low
    assert aps_active.passive_instrument_fraction < 0.2
    # Passive plan is ~95% index/bonds/ppf -> passive fraction should be high
    assert aps_passive.passive_instrument_fraction > 0.8
