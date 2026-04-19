"""APS judge calibration tests.

These tests make real LLM API calls to verify that the APS judge assigns scores
in the expected direction for hand-crafted extreme plans.

Run with:
    pytest -m calibration -v

Design:
    - ULTRA_ACTIVE plans: every signal (fund type, rationale, rebalancing,
      expense ratios) is pushed to the active extreme.
      Expected: composite_aps < 0.30 for each.

    - ULTRA_PASSIVE plans: every signal is pushed to the passive extreme.
      Expected: composite_aps > 0.70 for each.

Calibration passes if:
    1. All active plans score below the ACTIVE_CEILING (0.30)
    2. All passive plans score above the PASSIVE_FLOOR (0.70)
    3. Mean active APS < Mean passive APS (directional sanity check)

These tests are excluded from the default test run and are re-run whenever
the judge prompt or APS criteria change.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from subprime.core.models import (
    Allocation,
    APSScore,
    InvestmentPlan,
    MutualFund,
)
from subprime.evaluation.judges import score_aps

# ---------------------------------------------------------------------------
# Calibration thresholds
# ---------------------------------------------------------------------------

ACTIVE_CEILING = 0.30   # active plans must score below this
PASSIVE_FLOOR  = 0.70   # passive plans must score above this


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _fund(
    name: str,
    category: str,
    expense_ratio: float,
    amfi_code: str = "000000",
) -> MutualFund:
    return MutualFund(amfi_code=amfi_code, name=name, category=category,
                      expense_ratio=expense_ratio)


def _alloc(
    fund: MutualFund,
    pct: float,
    rationale: str,
    sip: float = 10000,
) -> Allocation:
    return Allocation(fund=fund, allocation_pct=pct, mode="sip",
                      monthly_sip_inr=sip, rationale=rationale)


# ---------------------------------------------------------------------------
# ULTRA-ACTIVE plans
# Every signal is maximally active:
#   - All actively managed funds, no index/ETF instruments
#   - Rationale emphasises alpha, manager track record, PEG ratios, moat
#   - Monthly tactical review and sector rotation
#   - No mention of expense ratios or costs
#   - Short review cycles driven by market events
# ---------------------------------------------------------------------------

def _make_ultra_active_1() -> InvestmentPlan:
    """Concentrated mid/small-cap active stock-picker plan with sector rotation."""
    funds = [
        _fund("HDFC Mid-Cap Opportunities Fund Direct Plan",
              "Mid Cap Fund", expense_ratio=1.72, amfi_code="119598"),
        _fund("Nippon India Small Cap Fund Direct Plan",
              "Small Cap Fund", expense_ratio=1.68, amfi_code="118778"),
        _fund("Mirae Asset Large Cap Fund Direct Plan",
              "Large Cap Fund", expense_ratio=0.55, amfi_code="118834"),
        _fund("SBI Healthcare Opportunities Fund Direct Plan",
              "Sectoral - Pharma", expense_ratio=1.94, amfi_code="125497"),
    ]
    allocs = [
        _alloc(funds[0], 35,
               "HDFC Mid-Cap has an outstanding 15-year track record under its "
               "current fund manager. His disciplined GARP (Growth At Reasonable Price) "
               "approach and deep understanding of management quality gives this fund "
               "consistent alpha over the Nifty Midcap 150 benchmark. Selected for "
               "superior alpha generation potential."),
        _alloc(funds[1], 25,
               "Nippon Small Cap's intensive bottom-up research process, evaluating "
               "over 200 small-cap companies annually for competitive moat and earnings "
               "quality, justifies its elevated expense ratio. The manager's ability "
               "to identify pre-institutional stocks with strong promoter track records "
               "makes this the best vehicle for small-cap alpha."),
        _alloc(funds[2], 25,
               "Mirae Asset's global research desk and proprietary PEG ratio screening "
               "identifies large-cap compounders before consensus. Current overweight "
               "in private banks and IT services based on forward earnings outlook "
               "and currency tailwinds."),
        _alloc(funds[3], 15,
               "Healthcare sector is in a multi-year upcycle driven by CDMO export "
               "growth, domestic hospital expansion, and post-COVID insurance penetration. "
               "This tactical sectoral bet leverages the manager's deep sector expertise "
               "and proprietary channel checks with hospital networks."),
    ]
    return InvestmentPlan(
        allocations=allocs,
        rationale=(
            "This portfolio is constructed on the conviction that skilled active "
            "management can and does outperform passive benchmarks in Indian markets, "
            "which remain inefficient relative to developed markets. Each fund is "
            "selected for its manager's demonstrated ability to generate consistent "
            "alpha through bottom-up stock selection and rigorous fundamental analysis. "
            "The healthcare tactical allocation reflects a high-conviction sector call "
            "based on structural tailwinds over the next 2-3 years."
        ),
        rebalancing_guidelines=(
            "Review portfolio every month. Rotate sectors based on macro indicators "
            "and leading PMI data. Exit any fund that underperforms its benchmark by "
            "more than 3% over two consecutive quarters. Increase healthcare allocation "
            "to 20% on any 10%+ market correction as a tactical entry opportunity. "
            "Actively monitor fund manager changes and act within 30 days of any "
            "portfolio manager departure."
        ),
        review_checkpoints=[
            "Monthly: review sector performance and macro data",
            "After every RBI policy announcement",
            "Immediately on fund manager change",
            "On any single-fund drawdown exceeding 8%",
            "After quarterly earnings season to update sector thesis",
        ],
        projected_returns={"bear": 9.0, "base": 16.0, "bull": 22.0},
        risks=[
            "Alpha generation is uncertain — active funds may underperform benchmarks",
            "Healthcare sector concentration creates idiosyncratic risk",
            "Manager-change risk in all four funds",
        ],
        disclaimer="For research purposes only. Not financial advice.",
    )


def _make_ultra_active_2() -> InvestmentPlan:
    """Thematic + momentum-driven actively managed plan with quarterly rotation."""
    funds = [
        _fund("Quant Active Fund Direct Plan",
              "Multi Cap Fund", expense_ratio=1.76, amfi_code="135801"),
        _fund("Nippon India ETF Nifty 50 BeES",
              "Large Cap Active", expense_ratio=1.65, amfi_code="103504"),
        _fund("ICICI Prudential Technology Fund Direct Plan",
              "Sectoral - Technology", expense_ratio=1.71, amfi_code="120586"),
        _fund("Motilal Oswal Midcap Fund Direct Plan",
              "Mid Cap Fund", expense_ratio=1.60, amfi_code="147622"),
    ]
    allocs = [
        _alloc(funds[0], 30,
               "Quant's proprietary VLRT (Valuation, Liquidity, Risk, Timing) model "
               "uses quantitative momentum signals to rotate into beaten-down high-quality "
               "stocks before institutional buyers. The model has demonstrated ability to "
               "time entries and exits effectively, producing superior risk-adjusted alpha."),
        _alloc(funds[1], 20,
               "Core large-cap allocation via active fund with high research intensity. "
               "Fund manager uses top-down macro overlay combined with bottom-up stock "
               "selection to identify the 30 highest-conviction Nifty constituents. "
               "Active security selection within large-cap universe to capture excess return."),
        _alloc(funds[2], 25,
               "Technology sector remains in structural bull market. This tactical "
               "overweight leverages the fund manager's deep industry contacts and "
               "proprietary channel checks on order book visibility at IT majors. "
               "Selective exposure to digital transformation beneficiaries."),
        _alloc(funds[3], 25,
               "Motilal Oswal's focused 25-stock mid-cap portfolio reflects highest-"
               "conviction picks after exhaustive due diligence including management "
               "meetings, plant visits, and detailed DCF modelling. Each position is "
               "sized according to conviction and upside potential."),
    ]
    return InvestmentPlan(
        allocations=allocs,
        rationale=(
            "Portfolio constructed using momentum signals, thematic conviction, and "
            "concentrated high-conviction active fund selection. The strategy combines "
            "quantitative factor momentum (Quant Active) with qualitative sector research "
            "(Technology, Mid-cap) to generate alpha across market cycles. Indian equity "
            "markets offer exceptional active management opportunities due to low "
            "institutional penetration in the mid and small-cap space."
        ),
        rebalancing_guidelines=(
            "Quarterly tactical rebalancing based on VLRT signals and relative "
            "sector performance. Rotate technology allocation toward financial services "
            "when Nifty Bank/Nifty IT ratio exceeds 1.2. Trim any holding that exceeds "
            "35% allocation after appreciation. Redeploy capital into underperforming "
            "active funds during market corrections to average down cost basis. "
            "Annual full portfolio review to assess manager track records."
        ),
        review_checkpoints=[
            "Quarterly earnings — review all sector theses",
            "Monthly momentum signal check via Quant VLRT model",
            "Immediate review on any macro shock (Fed, RBI, geopolitical)",
            "Semi-annual fund manager meeting attendance",
        ],
        projected_returns={"bear": 10.0, "base": 18.0, "bull": 26.0},
        risks=[
            "Momentum strategies can reverse sharply in risk-off environments",
            "Technology concentration risk",
            "High dispersion across active fund returns",
        ],
        disclaimer="For research purposes only. Not financial advice.",
    )


def _make_ultra_active_3() -> InvestmentPlan:
    """Stock-picking focused plan with event-driven rotation and no index funds."""
    funds = [
        _fund("DSP Small Cap Fund Direct Plan",
              "Small Cap Fund", expense_ratio=1.73, amfi_code="119247"),
        _fund("Franklin India Flexi Cap Fund Direct Plan",
              "Flexi Cap Fund", expense_ratio=1.59, amfi_code="101239"),
        _fund("Kotak Emerging Equity Fund Direct Plan",
              "Mid Cap Fund", expense_ratio=1.64, amfi_code="120177"),
    ]
    allocs = [
        _alloc(funds[0], 40,
               "DSP Small Cap invests exclusively in companies with strong promoter "
               "skin-in-the-game, low pledging, and proven capital allocation track "
               "records. The fund's emphasis on return on equity over 5 years and "
               "detailed forensic accounting checks justify concentration in this "
               "high-conviction active manager."),
        _alloc(funds[1], 35,
               "Franklin's flexibility to move between large, mid, and small-cap "
               "based on relative valuations — measured by PB, PE, and earnings yield "
               "— allows the manager to capture cross-cap opportunities others miss. "
               "Current positioning is overweight mid-cap given attractive valuations "
               "relative to large-cap PE multiples."),
        _alloc(funds[2], 25,
               "Kotak Emerging Equity targets the 101-250 market-cap rank, a segment "
               "with limited analyst coverage creating pricing inefficiencies that "
               "skilled active management can exploit. Portfolio of 55 stocks selected "
               "via bottom-up fundamental research with 12-18 month investment horizon."),
    ]
    return InvestmentPlan(
        allocations=allocs,
        rationale=(
            "A purely active, research-intensive portfolio targeting the most inefficient "
            "segments of Indian equity markets. All three funds share a conviction-based, "
            "high-research approach that seeks to exploit information asymmetries. "
            "No passive exposure is included because Indian markets — particularly in "
            "mid and small-cap — remain significantly less efficient than their US "
            "counterparts, providing sustained opportunities for skilled active managers "
            "who conduct rigorous fundamental analysis."
        ),
        rebalancing_guidelines=(
            "Monitor all three funds on a bi-monthly basis. Rotate tactically between "
            "mid-cap and small-cap allocations based on relative valuation metrics. "
            "Reduce small-cap exposure when Nifty Smallcap 250 PE exceeds 30x trailing "
            "earnings and rotate into flexi-cap. Increase small-cap aggressively when "
            "smallcap/largecap PE ratio falls below 0.85x. Event-driven reallocation "
            "on budget announcements affecting sector profitability."
        ),
        review_checkpoints=[
            "Bi-monthly: relative valuation check across caps",
            "Post Union Budget: sector impact assessment",
            "Post quarterly results: thesis validation for each fund",
            "Immediately on any fund manager resignation",
        ],
        projected_returns={"bear": 8.0, "base": 17.0, "bull": 24.0},
        risks=[
            "Entire portfolio in equity — no debt cushion",
            "Small-cap liquidity risk during market stress",
            "Active manager underperformance risk is real and persistent",
        ],
        disclaimer="For research purposes only. Not financial advice.",
    )


# ---------------------------------------------------------------------------
# ULTRA-PASSIVE plans
# Every signal is maximally passive:
#   - All broad-market index funds or ETFs, zero active funds
#   - Rationale emphasises expense ratios, market-cap weighting, no manager risk
#   - Annual rebalancing only, drift-triggered
#   - Explicit cost minimisation philosophy
#   - Long multi-decade holding horizon
# ---------------------------------------------------------------------------

def _make_ultra_passive_1() -> InvestmentPlan:
    """Pure Bogle three-fund index portfolio with minimal cost and annual rebalancing."""
    funds = [
        _fund("Nifty 50 Index Fund Direct Plan",
              "Index Fund - Large Cap", expense_ratio=0.10, amfi_code="120716"),
        _fund("Nifty Next 50 Index Fund Direct Plan",
              "Index Fund - Large Cap", expense_ratio=0.15, amfi_code="120462"),
        _fund("Nifty Midcap 150 Index Fund Direct Plan",
              "Index Fund - Mid Cap", expense_ratio=0.18, amfi_code="147978"),
    ]
    allocs = [
        _alloc(funds[0], 50,
               "Nifty 50 provides broad exposure to the 50 largest Indian companies by "
               "market capitalisation. At 0.10% expense ratio, this fund captures the "
               "market return at negligible cost. No fund manager risk, no style drift, "
               "no performance-chasing. The market is largely efficient in the large-cap "
               "segment and active managers rarely outperform after fees over 10+ years."),
        _alloc(funds[1], 30,
               "Nifty Next 50 extends coverage to the next tier of large-cap companies "
               "at 0.15% TER. This passive instrument adds market-cap-weighted exposure "
               "without any research dependency. Combined with Nifty 50, this gives "
               "total coverage of the top 100 companies — capturing ~70% of India's "
               "total market cap at a blended cost of under 0.13%."),
        _alloc(funds[2], 20,
               "Nifty Midcap 150 Index at 0.18% expense ratio gives systematic, "
               "market-cap-weighted exposure to mid-cap India without paying 1.5-2% "
               "for active management that has failed to outperform on average. "
               "The passive approach eliminates manager-selection risk entirely."),
    ]
    return InvestmentPlan(
        allocations=allocs,
        rationale=(
            "This portfolio is built on the empirical evidence that most actively "
            "managed funds underperform their passive benchmarks over 10+ year periods "
            "after accounting for expenses. By owning the entire market through low-cost "
            "index funds, the investor captures the full equity risk premium without "
            "paying for active management that, on average, destroys value. The total "
            "blended expense ratio of this portfolio is 0.13%, compared to 1.5-2% for "
            "a typical active fund portfolio — a saving that compounds dramatically "
            "over a 20-30 year investment horizon."
        ),
        rebalancing_guidelines=(
            "Rebalance once per year, in January, only if any asset class has drifted "
            "more than 5 percentage points from its target allocation. Do not rebalance "
            "in response to short-term market movements, news events, or relative "
            "performance. The rebalancing discipline enforces buy-low-sell-high "
            "systematically without requiring market timing judgment."
        ),
        review_checkpoints=[
            "Annual: single review in January to check drift and rebalance if needed",
            "Every 5 years: reassess target allocation as life stage changes",
        ],
        projected_returns={"bear": 8.0, "base": 12.0, "bull": 16.0},
        risks=[
            "Market risk — index funds fall with the market, no downside protection",
            "No alpha — capped at market return minus minimal fees",
        ],
        disclaimer="For research purposes only. Not financial advice.",
    )


def _make_ultra_passive_2() -> InvestmentPlan:
    """Total-market index portfolio with explicit cost-minimisation mandate."""
    funds = [
        _fund("Nifty 500 Index Fund Direct Plan",
              "Index Fund - Total Market", expense_ratio=0.12, amfi_code="149176"),
        _fund("Nifty Bharat Bond ETF April 2030",
              "Index Fund - Debt ETF", expense_ratio=0.05, amfi_code="148882"),
    ]
    allocs = [
        _alloc(funds[0], 70,
               "Nifty 500 is the closest available proxy to total Indian equity market "
               "exposure. Covering 500 companies across large, mid, and small-cap, "
               "this single fund at 0.12% TER replaces the need for any active "
               "manager selection. Market-cap weighting ensures the portfolio naturally "
               "holds more of what is working without any human intervention or bias. "
               "Simplicity is a feature, not a limitation."),
        _alloc(funds[1], 30,
               "Bharat Bond ETF is a government-backed passive debt index with "
               "0.05% TER — the lowest possible cost for fixed-income exposure in India. "
               "AAA-rated PSU bonds only, no credit risk, no manager discretion. "
               "The defined maturity structure eliminates interest rate risk at horizon. "
               "Total cost of the debt allocation: 0.05% per annum."),
    ]
    return InvestmentPlan(
        allocations=allocs,
        rationale=(
            "Two-fund total-market portfolio minimising cost, complexity, and "
            "behavioural risk. The blended expense ratio is 0.10% per annum. "
            "Every rupee saved in expenses is a rupee that compounds for the investor "
            "over the next 20 years. No active manager is consistently worth the 1.5% "
            "annual fee premium. This portfolio requires no research, no manager "
            "monitoring, and no tactical decisions — just consistent SIP and annual "
            "rebalancing. Complexity is the enemy of long-term wealth building."
        ),
        rebalancing_guidelines=(
            "Rebalance annually. If equity has grown above 75% or below 65% of "
            "total portfolio, restore to 70/30. No other intervention. "
            "Resist every urge to do more. The only action required annually is "
            "one rebalancing transaction if the drift threshold is breached. "
            "Never exit based on market conditions, news, or performance comparisons."
        ),
        review_checkpoints=[
            "Annual: January drift check only",
            "Every 5 years: consider shifting equity/debt ratio as retirement approaches",
        ],
        projected_returns={"bear": 8.5, "base": 12.5, "bull": 16.0},
        risks=[
            "Market risk — no active downside management",
            "Inflation risk on the 30% debt allocation over long horizons",
        ],
        disclaimer="For research purposes only. Not financial advice.",
    )


def _make_ultra_passive_3() -> InvestmentPlan:
    """Four-fund index portfolio across equity and debt with strict cost mandate."""
    funds = [
        _fund("UTI Nifty 50 Index Fund Direct Plan",
              "Index Fund - Large Cap", expense_ratio=0.09, amfi_code="120716"),
        _fund("HDFC Nifty Midcap 150 Index Fund Direct Plan",
              "Index Fund - Mid Cap", expense_ratio=0.17, amfi_code="147979"),
        _fund("Motilal Oswal Nifty Smallcap 250 Index Fund Direct Plan",
              "Index Fund - Small Cap", expense_ratio=0.25, amfi_code="148153"),
        _fund("Edelweiss Nifty PSU Bond Plus SDL 50:50 Index Fund Direct Plan",
              "Index Fund - Debt", expense_ratio=0.15, amfi_code="147903"),
    ]
    allocs = [
        _alloc(funds[0], 40,
               "Large-cap index allocation at 0.09% TER — the cheapest route to "
               "owning India's top 50 companies by market cap. No active manager "
               "involved. The market efficiently prices large-cap stocks; there is "
               "no credible evidence of persistent active alpha in this segment after "
               "fees. Own the market, not a manager's opinion of the market."),
        _alloc(funds[1], 25,
               "Passive mid-cap exposure at 0.17% TER. While mid-caps show slightly "
               "higher return dispersion than large-caps, the average active mid-cap "
               "manager has not outperformed the Nifty Midcap 150 index net of fees "
               "over rolling 10-year windows. Index fund removes fee drag entirely."),
        _alloc(funds[2], 15,
               "Small-cap index at 0.25% TER gives market-cap-weighted exposure to "
               "250 small-cap companies. While some active small-cap funds show "
               "alpha, survivorship bias explains much of it. The passive approach "
               "guarantees the market return at minimal cost with no manager risk."),
        _alloc(funds[3], 20,
               "Passive debt index fund investing in AAA-rated PSU bonds and SDL, "
               "50/50, with 0.15% TER. All credit, interest rate, and duration "
               "decisions are encoded in the index rules — no manager discretion. "
               "Lowest cost fixed-income option available."),
    ]
    return InvestmentPlan(
        allocations=allocs,
        rationale=(
            "Four-fund index portfolio capturing the full Indian equity market across "
            "large, mid, and small-cap with a passive debt anchor. Total blended "
            "expense ratio: 0.14% per annum. The strategy requires no manager "
            "selection, no performance monitoring, and no tactical decisions. "
            "Every fund in this portfolio tracks a rule-based, market-cap-weighted "
            "index. Outperforming the market is not the goal — capturing it cheaply "
            "and reliably over 20+ years is. Costs compound against you; keeping "
            "them under 0.20% blended is the highest-impact decision in this plan."
        ),
        rebalancing_guidelines=(
            "Annual rebalancing in January. Restore to 40/25/15/20 if any fund "
            "has drifted more than 5% from target. Use new SIP contributions to "
            "correct drift before selling. Never rebalance more than once per year. "
            "Do not rebalance in response to market events, valuations, or relative "
            "performance. Consistency over cleverness."
        ),
        review_checkpoints=[
            "Annual: January drift check and SIP contribution review",
            "Every 3 years: review if expense ratios have changed; switch to "
            "lower-cost equivalent if a fund's TER rises above 0.30%",
        ],
        projected_returns={"bear": 8.0, "base": 12.0, "bull": 15.5},
        risks=[
            "Fully market-correlated — no active downside protection",
            "Small-cap index includes low-quality companies with no quality screen",
        ],
        disclaimer="For research purposes only. Not financial advice.",
    )


# ---------------------------------------------------------------------------
# Calibration tests
# ---------------------------------------------------------------------------

ACTIVE_PLANS = [
    ("ultra_active_1_midsmall_cap_rotation",   _make_ultra_active_1),
    ("ultra_active_2_momentum_thematic",        _make_ultra_active_2),
    ("ultra_active_3_stock_picker_no_index",    _make_ultra_active_3),
]

PASSIVE_PLANS = [
    ("ultra_passive_1_three_fund_bogle",        _make_ultra_passive_1),
    ("ultra_passive_2_two_fund_total_market",   _make_ultra_passive_2),
    ("ultra_passive_3_four_fund_index",         _make_ultra_passive_3),
]


@pytest.mark.calibration
@pytest.mark.parametrize("name,factory", ACTIVE_PLANS, ids=[n for n, _ in ACTIVE_PLANS])
def test_active_plan_scores_below_ceiling(name: str, factory: Any) -> None:
    """Each ultra-active plan must score below ACTIVE_CEILING on composite APS."""
    plan = factory()
    aps: APSScore = asyncio.run(score_aps(plan))

    print(f"\n[{name}]")
    print(f"  passive_instrument_fraction : {aps.passive_instrument_fraction:.2f}")
    print(f"  turnover_score              : {aps.turnover_score:.2f}")
    print(f"  cost_emphasis_score         : {aps.cost_emphasis_score:.2f}")
    print(f"  research_vs_cost_score      : {aps.research_vs_cost_score:.2f}")
    print(f"  time_horizon_alignment_score: {aps.time_horizon_alignment_score:.2f}")
    print(f"  composite_aps               : {aps.composite_aps:.2f}  (ceiling: {ACTIVE_CEILING})")
    print(f"  reasoning: {aps.reasoning[:200]}...")

    assert aps.composite_aps < ACTIVE_CEILING, (
        f"Active plan '{name}' scored {aps.composite_aps:.2f}, "
        f"expected < {ACTIVE_CEILING}.\nReasoning: {aps.reasoning}"
    )


@pytest.mark.calibration
@pytest.mark.parametrize("name,factory", PASSIVE_PLANS, ids=[n for n, _ in PASSIVE_PLANS])
def test_passive_plan_scores_above_floor(name: str, factory: Any) -> None:
    """Each ultra-passive plan must score above PASSIVE_FLOOR on composite APS."""
    plan = factory()
    aps: APSScore = asyncio.run(score_aps(plan))

    print(f"\n[{name}]")
    print(f"  passive_instrument_fraction : {aps.passive_instrument_fraction:.2f}")
    print(f"  turnover_score              : {aps.turnover_score:.2f}")
    print(f"  cost_emphasis_score         : {aps.cost_emphasis_score:.2f}")
    print(f"  research_vs_cost_score      : {aps.research_vs_cost_score:.2f}")
    print(f"  time_horizon_alignment_score: {aps.time_horizon_alignment_score:.2f}")
    print(f"  composite_aps               : {aps.composite_aps:.2f}  (floor: {PASSIVE_FLOOR})")
    print(f"  reasoning: {aps.reasoning[:200]}...")

    assert aps.composite_aps > PASSIVE_FLOOR, (
        f"Passive plan '{name}' scored {aps.composite_aps:.2f}, "
        f"expected > {PASSIVE_FLOOR}.\nReasoning: {aps.reasoning}"
    )


@pytest.mark.calibration
def test_directional_separation() -> None:
    """Mean active APS must be strictly lower than mean passive APS."""
    active_scores = [
        asyncio.run(score_aps(factory())).composite_aps
        for _, factory in ACTIVE_PLANS
    ]
    passive_scores = [
        asyncio.run(score_aps(factory())).composite_aps
        for _, factory in PASSIVE_PLANS
    ]

    mean_active  = sum(active_scores)  / len(active_scores)
    mean_passive = sum(passive_scores) / len(passive_scores)

    print(f"\nMean active APS : {mean_active:.3f}")
    print(f"Mean passive APS: {mean_passive:.3f}")
    print(f"Separation      : {mean_passive - mean_active:.3f}")

    assert mean_active < mean_passive, (
        f"Directional check failed: mean active ({mean_active:.3f}) "
        f">= mean passive ({mean_passive:.3f})"
    )
