"""End-to-end tests — hits real APIs, requires ANTHROPIC_API_KEY.

Run with: uv run pytest tests/test_e2e.py -v -m e2e
Skip in normal runs: uv run pytest -m 'not e2e'
"""
import os

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def skip_without_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY") or os.environ["ANTHROPIC_API_KEY"].startswith("sk-ant-..."):
        pytest.skip("ANTHROPIC_API_KEY not set — skipping e2e test")


class TestLiveMFDataAPI:
    """Verify our client works against the real mfdata.in API."""

    async def test_search_funds_live(self):
        from subprime.data.tools import search_funds

        results = await search_funds("nifty 50 index")
        assert len(results) > 0
        # Should return real fund data
        fund = results[0]
        assert fund.amfi_code
        assert fund.name
        assert fund.nav > 0

    async def test_get_fund_performance_live(self):
        from subprime.data.tools import get_fund_performance

        # UTI Nifty 50 Index Fund - Direct Plan - Growth
        fund = await get_fund_performance("120716")
        assert fund.amfi_code == "120716"
        assert fund.nav > 0
        assert fund.expense_ratio >= 0


class TestFullAdvisorFlow:
    """Full advisor flow: profile -> strategy -> plan -> scores."""

    async def test_happy_path(self):
        from subprime.advisor.planner import generate_plan, generate_strategy
        from subprime.core.models import InvestmentPlan, StrategyOutline
        from subprime.evaluation.personas import get_persona
        from subprime.evaluation.scorer import score_plan, ScoredPlan

        profile = get_persona("P01")

        # Phase 2: Generate strategy (real LLM call)
        strategy = await generate_strategy(profile)
        assert isinstance(strategy, StrategyOutline)
        assert strategy.equity_pct >= 0
        assert strategy.equity_pct <= 100
        assert len(strategy.key_themes) > 0

        # Phase 3: Generate plan with real fund data (real LLM + real API)
        plan = await generate_plan(profile, strategy=strategy)
        assert isinstance(plan, InvestmentPlan)
        assert len(plan.allocations) > 0
        # Should have real fund names
        assert plan.allocations[0].fund.amfi_code
        assert plan.allocations[0].fund.nav > 0

        # Score the plan (real LLM calls)
        scored = await score_plan(plan, profile)
        assert isinstance(scored, ScoredPlan)
        assert 0 <= scored.aps.composite_aps <= 1
        assert 0 <= scored.pqs.composite_pqs <= 1
