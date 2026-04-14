"""Judging criteria as structured data for APS and PQS scoring.

Criteria are dictionaries — not hardcoded prompts — so they can be
programmatically assembled into judge prompts and independently tested.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# APS (Active-Passive Score) criteria — 5 dimensions
# ---------------------------------------------------------------------------

APS_CRITERIA: dict[str, dict[str, str]] = {
    "passive_instrument_fraction": {
        "description": (
            "What fraction of the plan's total allocation is directed toward "
            "passive/index instruments (index funds, ETFs, target-date funds) "
            "versus actively managed funds or individual stocks?"
        ),
        "anchor_0": (
            "0.0 = Entirely active: all allocations are to individual stocks "
            "or actively managed funds with stock-picking mandates"
        ),
        "anchor_1": (
            "1.0 = Entirely passive: all allocations are to broad-market index "
            "funds, index ETFs, or passive target-date funds"
        ),
    },
    "turnover_score": {
        "description": (
            "How frequently does the plan recommend portfolio rebalancing, "
            "tactical shifts, or active trading? Consider the rebalancing "
            "guidelines and review checkpoints."
        ),
        "anchor_0": (
            "0.0 = Frequent rebalancing: monthly or quarterly tactical shifts, "
            "active sector rotation, or momentum-based trading"
        ),
        "anchor_1": (
            "1.0 = Buy-and-hold: annual or less frequent rebalancing, minimal "
            "tactical adjustments, long-term static allocation"
        ),
    },
    "cost_emphasis_score": {
        "description": (
            "How much does the plan emphasise minimising costs — expense ratios, "
            "transaction fees, tax efficiency — as a primary decision criterion?"
        ),
        "anchor_0": (
            "0.0 = No cost mention: costs are not discussed; fund selection is "
            "driven by expected alpha or thematic conviction"
        ),
        "anchor_1": (
            "1.0 = Cost is primary criterion: expense ratios are the dominant "
            "selection factor; the plan explicitly minimises total cost of ownership"
        ),
    },
    "research_vs_cost_score": {
        "description": (
            "Does the plan emphasise deep, stock-specific or fund-specific research "
            "(company analysis, sector expertise, manager track records) or does it "
            "favour broad market exposure without individual security research?"
        ),
        "anchor_0": (
            "0.0 = Deep research: detailed company/sector analysis, PEG ratios, "
            "management quality, competitive moat evaluation for each pick"
        ),
        "anchor_1": (
            "1.0 = No research, broad market: relies on market-cap-weighted indices "
            "or total-market funds; no individual security analysis"
        ),
    },
    "time_horizon_alignment_score": {
        "description": (
            "Is the recommended strategy consistent with a long-term, patient "
            "investment horizon, or does it imply short-term opportunistic moves?"
        ),
        "anchor_0": (
            "0.0 = Short-term orientation: strategy implies frequent review cycles, "
            "tactical windows, or event-driven positioning"
        ),
        "anchor_1": (
            "1.0 = Long-term orientation: strategy is designed for decades-long "
            "compounding with infrequent intervention"
        ),
    },
    "portfolio_activeness_score": {
        "description": (
            "Using the quantitative risk metrics provided for each fund (beta, alpha, "
            "tracking error, information ratio) — does the recommended portfolio "
            "reflect genuine active conviction or index-like passive exposure? "
            "Beta close to 1.0 and tracking error below 3% indicate a closet indexer "
            "regardless of its category label. High tracking error (>10%) with positive "
            "alpha indicates genuine active management. Score the portfolio-weighted "
            "average activeness based on these metrics, not just category names."
        ),
        "anchor_0": (
            "0.0 = Genuinely active: portfolio of high-alpha, high-tracking-error funds "
            "with concentrated bets, beta > 1.0, information ratio > 0.5. "
            "Funds deviate substantially from the Nifty 50 benchmark."
        ),
        "anchor_1": (
            "1.0 = Truly passive: portfolio of index funds or closet indexers with "
            "beta ≈ 1.0, tracking error < 2%, alpha ≈ 0%, minimal deviation from benchmark. "
            "If risk metrics are absent, infer from category and rationale."
        ),
    },
}

# ---------------------------------------------------------------------------
# PQS (Plan Quality Score) criteria — 4 dimensions
# ---------------------------------------------------------------------------

PQS_CRITERIA: dict[str, dict[str, str]] = {
    "goal_alignment": {
        "description": (
            "How well does the plan's asset allocation, fund selection, and "
            "projected timeline align with the investor's stated financial goals, "
            "life stage, and investment horizon?"
        ),
        "anchor_0": (
            "0.0 = No alignment: the plan ignores the investor's goals, time "
            "horizon, or life stage entirely"
        ),
        "anchor_1": (
            "1.0 = Perfect alignment: every allocation decision is clearly "
            "justified by the investor's specific goals and circumstances"
        ),
    },
    "diversification": {
        "description": (
            "Does the plan provide adequate diversification across asset classes, "
            "sectors, geographies, and fund houses to manage concentration risk?"
        ),
        "anchor_0": (
            "0.0 = No diversification: single fund, single asset class, or "
            "extreme concentration in one sector/geography"
        ),
        "anchor_1": (
            "1.0 = Excellent diversification: broad coverage across asset classes, "
            "sectors, geographies, and fund houses with appropriate weightings"
        ),
    },
    "risk_return_appropriateness": {
        "description": (
            "Is the plan's risk-return profile appropriate for the investor's "
            "risk appetite? Consider whether projected returns are realistic and "
            "whether downside scenarios are adequately addressed."
        ),
        "anchor_0": (
            "0.0 = Inappropriate: risk level is wildly mismatched with the "
            "investor's stated appetite (e.g., aggressive plan for conservative "
            "investor), or projected returns are unrealistic"
        ),
        "anchor_1": (
            "1.0 = Perfectly appropriate: risk exposure matches the investor's "
            "appetite precisely, projections are realistic, and downside "
            "scenarios are well-addressed"
        ),
    },
    "internal_consistency": {
        "description": (
            "Is the plan internally consistent? Do the rationale, fund selections, "
            "allocation percentages, rebalancing guidelines, and risk warnings "
            "tell a coherent story without contradictions?"
        ),
        "anchor_0": (
            "0.0 = Contradictory: rationale says one thing but allocations do "
            "another; risk warnings contradict the strategy; numbers don't add up"
        ),
        "anchor_1": (
            "1.0 = Fully consistent: every element of the plan supports the "
            "stated strategy; no contradictions between rationale, allocations, "
            "and risk assessment"
        ),
    },
}
