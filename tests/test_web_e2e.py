"""Playwright E2E tests for the FinAdvisor wizard.

These run a real Chromium browser against the FastAPI app with mocked LLM calls.
They catch issues that httpx tests miss: broken buttons, HTMX swaps, JS errors,
loading states, navigation, and full user flows.

Run: pytest tests/test_web_e2e.py -v
Requires: pip install pytest-playwright && playwright install chromium
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, patch

import pytest
import uvicorn

from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    MutualFund,
    StrategyOutline,
)


# ---------------------------------------------------------------------------
# Fixtures: mock data
# ---------------------------------------------------------------------------


def _mock_strategy() -> StrategyOutline:
    return StrategyOutline(
        equity_pct=70,
        debt_pct=20,
        gold_pct=10,
        other_pct=0,
        equity_approach="Mix of large cap index and mid cap active funds",
        key_themes=["diversification", "long-term growth"],
        risk_return_summary="Expected 11-12% CAGR with moderate drawdowns",
        open_questions=[],
    )


def _mock_plan() -> InvestmentPlan:
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(
                    amfi_code="119551",
                    name="UTI Nifty 50 Index Fund",
                    category="Large Cap",
                    fund_house="UTI",
                    expense_ratio=0.18,
                    morningstar_rating=4,
                ),
                allocation_pct=40,
                mode="sip",
                monthly_sip_inr=20000,
                rationale="Low cost large cap index fund for core equity exposure",
            ),
            Allocation(
                fund=MutualFund(
                    amfi_code="120505",
                    name="Parag Parikh Flexi Cap Fund",
                    category="Flexi Cap",
                    fund_house="PPFAS",
                    expense_ratio=0.63,
                    morningstar_rating=5,
                ),
                allocation_pct=30,
                mode="sip",
                monthly_sip_inr=15000,
                rationale="Diversified flexi cap with international exposure",
            ),
            Allocation(
                fund=MutualFund(
                    amfi_code="119533",
                    name="HDFC Short Term Debt Fund",
                    category="Short Duration",
                    fund_house="HDFC",
                    expense_ratio=0.35,
                ),
                allocation_pct=30,
                mode="sip",
                monthly_sip_inr=15000,
                rationale="Stable debt allocation for risk management",
            ),
        ],
        projected_returns={"bear": 7.5, "base": 11.0, "bull": 15.0},
        rationale="This plan balances growth and stability for a moderate risk investor.",
        risks=[
            "Market drops can be 20-30%",
            "Debt funds can lose value if interest rates rise",
        ],
        setup_phase="1. Open account on Kuvera\n2. Start SIPs in all three funds",
        rebalancing_guidelines="Check once a year. Rebalance if equity drifts beyond 75%.",
    )


# ---------------------------------------------------------------------------
# Fixtures: app server
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _patched_app():
    """Create the FastAPI app with LLM calls mocked."""
    mock_strat = AsyncMock(return_value=_mock_strategy())
    mock_plan = AsyncMock(return_value=_mock_plan())

    with (
        patch("apps.web.api.generate_strategy", mock_strat),
        patch("apps.web.api.generate_plan", mock_plan),
    ):
        from apps.web.main import create_app

        app = create_app()
        yield app


@pytest.fixture(scope="session")
def base_url(_patched_app):
    """Start the FastAPI app in a background thread and return the base URL."""
    host = "127.0.0.1"
    port = 18091  # Use a non-standard port to avoid conflicts

    config = uvicorn.Config(
        app=_patched_app, host=host, port=port, log_level="warning"
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for the server to start
    import time
    import httpx

    for _ in range(30):
        try:
            resp = httpx.get(f"http://{host}:{port}/step/1", timeout=1)
            if resp.status_code == 200:
                break
        except httpx.ConnectError:
            time.sleep(0.5)
    else:
        pytest.fail("Server did not start within 15 seconds")

    yield f"http://{host}:{port}"

    server.should_exit = True
    thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestWizardE2E:
    """Full browser-based E2E tests for the wizard flow."""

    def test_step1_renders_tier_cards(self, page, base_url):
        """Step 1 shows Basic and Premium tier cards."""
        page.goto(f"{base_url}/step/1")
        assert page.title() == "Choose Your Plan — FinAdvisor"

        # Both cards visible
        assert page.locator("text=Basic").first.is_visible()
        assert page.locator("text=Premium").first.is_visible()
        assert page.locator("text=Start Free Plan").is_visible()
        assert page.locator("text=Start Premium Plan").is_visible()

    def test_step1_disclaimer_visible(self, page, base_url):
        """Step 1 shows the SEBI disclaimer."""
        page.goto(f"{base_url}/step/1")
        assert page.locator("text=not registered with SEBI").is_visible()

    def test_step1_basic_navigates_to_step2(self, page, base_url):
        """Clicking 'Start Free Plan' navigates to Step 2."""
        page.goto(f"{base_url}/step/1")
        page.locator("text=Start Free Plan").click()
        page.wait_for_url("**/step/2")
        assert "/step/2" in page.url

    def test_step2_shows_persona_cards(self, page, base_url):
        """Step 2 shows persona cards with investor details."""
        page.goto(f"{base_url}/step/1")
        page.locator("text=Start Free Plan").click()
        page.wait_for_url("**/step/2")

        # Persona P01 should be visible
        assert page.locator("text=Arjun Mehta").is_visible()

    def test_step2_custom_profile_tab(self, page, base_url):
        """Switching to Custom Profile tab shows the form."""
        page.goto(f"{base_url}/step/1")
        page.locator("text=Start Free Plan").click()
        page.wait_for_url("**/step/2")

        # Click Custom Profile tab
        page.locator("text=Custom Profile").click()

        # Form fields should be visible
        assert page.locator("input[name='name']").is_visible()
        assert page.locator("input[name='age']").is_visible()
        assert page.locator("input[name='monthly_sip']").is_visible()

    def test_step2_persona_navigates_to_step3(self, page, base_url):
        """Clicking a persona card navigates to Step 3."""
        page.goto(f"{base_url}/step/1")
        page.locator("text=Start Free Plan").click()
        page.wait_for_url("**/step/2")

        # Click the first persona card (Arjun Mehta)
        page.locator("text=Arjun Mehta").click()
        page.wait_for_url("**/step/3")
        assert "/step/3" in page.url

    def test_step3_loads_strategy_dashboard(self, page, base_url):
        """Step 3 generates strategy and shows the dashboard."""
        page.goto(f"{base_url}/step/1")
        page.locator("text=Start Free Plan").click()
        page.wait_for_url("**/step/2")
        page.locator("text=Arjun Mehta").click()
        page.wait_for_url("**/step/3")

        # Strategy dashboard should load via HTMX (wait for it)
        page.wait_for_selector("text=Equity Approach", timeout=10000)
        assert page.locator("text=Equity Approach").is_visible()
        assert page.locator("text=Key Themes").is_visible()
        assert page.locator("text=Generate My Plan").is_visible()

    def test_step3_generate_plan_navigates_to_step4(self, page, base_url):
        """Clicking 'Generate My Plan' navigates to Step 4."""
        page.goto(f"{base_url}/step/1")
        page.locator("text=Start Free Plan").click()
        page.wait_for_url("**/step/2")
        page.locator("text=Arjun Mehta").click()
        page.wait_for_url("**/step/3")

        # Wait for strategy to load
        page.wait_for_selector("text=Generate My Plan", timeout=10000)

        # Click Generate My Plan
        page.locator("text=Generate My Plan").click()

        # Should navigate to step 4 (mock is fast, so spinner may flash by)
        page.wait_for_url("**/step/4", timeout=30000)
        assert "/step/4" in page.url

    def test_step4_shows_plan_results(self, page, base_url):
        """Step 4 shows fund allocations, projections, and rationale."""
        # Navigate through full flow
        page.goto(f"{base_url}/step/1")
        page.locator("text=Start Free Plan").click()
        page.wait_for_url("**/step/2")
        page.locator("text=Arjun Mehta").click()
        page.wait_for_url("**/step/3")
        page.wait_for_selector("text=Generate My Plan", timeout=10000)
        page.locator("text=Generate My Plan").click()
        page.wait_for_url("**/step/4", timeout=30000)

        # Fund names from mock data should appear
        assert page.locator("text=UTI Nifty 50 Index Fund").is_visible()
        assert page.locator("text=Parag Parikh Flexi Cap Fund").is_visible()
        assert page.locator("text=HDFC Short Term Debt Fund").is_visible()

        # Stat cards
        assert page.locator("text=Monthly SIP").is_visible()

        # Rationale section
        assert page.locator("text=Why This Plan").is_visible()

    def test_step4_expandable_fund_rationale(self, page, base_url):
        """Fund allocation rows expand to show rationale."""
        page.goto(f"{base_url}/step/1")
        page.locator("text=Start Free Plan").click()
        page.wait_for_url("**/step/2")
        page.locator("text=Arjun Mehta").click()
        page.wait_for_url("**/step/3")
        page.wait_for_selector("text=Generate My Plan", timeout=10000)
        page.locator("text=Generate My Plan").click()
        page.wait_for_url("**/step/4", timeout=30000)

        # Click on a fund to expand rationale
        page.locator("text=UTI Nifty 50 Index Fund").click()

        # Rationale text should appear
        page.wait_for_selector("text=Low cost large cap", timeout=3000)
        assert page.locator("text=Low cost large cap").is_visible()

    def test_step4_start_over(self, page, base_url):
        """'Start Over' button returns to Step 1."""
        page.goto(f"{base_url}/step/1")
        page.locator("text=Start Free Plan").click()
        page.wait_for_url("**/step/2")
        page.locator("text=Arjun Mehta").click()
        page.wait_for_url("**/step/3")
        page.wait_for_selector("text=Generate My Plan", timeout=10000)
        page.locator("text=Generate My Plan").click()
        page.wait_for_url("**/step/4", timeout=30000)

        # Click Start Over
        page.locator("text=Start Over").click()
        page.wait_for_url("**/step/1", timeout=5000)
        assert "/step/1" in page.url

    def test_step_indicator_present(self, page, base_url):
        """Step indicator is present with step labels in page content."""
        page.goto(f"{base_url}/step/1")
        content = page.content()
        assert "Choose Plan" in content
        assert "Your Profile" in content
        assert "Strategy" in content
        assert "Your Plan" in content

    def test_premium_flow(self, page, base_url):
        """Premium tier selection flows through the same wizard."""
        page.goto(f"{base_url}/step/1")
        page.locator("text=Start Premium Plan").click()
        page.wait_for_url("**/step/2")
        page.locator("text=Arjun Mehta").click()
        page.wait_for_url("**/step/3")
        page.wait_for_selector("text=Generate My Plan", timeout=10000)
        assert page.locator("text=Generate My Plan").is_visible()

    def test_no_js_console_errors(self, page, base_url):
        """No JavaScript console errors during the full flow."""
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

        page.goto(f"{base_url}/step/1")
        page.locator("text=Start Free Plan").click()
        page.wait_for_url("**/step/2")
        page.locator("text=Arjun Mehta").click()
        page.wait_for_url("**/step/3")
        page.wait_for_selector("text=Generate My Plan", timeout=10000)
        page.locator("text=Generate My Plan").click()
        page.wait_for_url("**/step/4", timeout=30000)

        # Filter out known benign errors (e.g., Chart.js warnings)
        real_errors = [e for e in errors if "Chart" not in e]
        assert real_errors == [], f"JS console errors: {real_errors}"

    def test_navigation_guard_step3(self, page, base_url):
        """Navigating directly to Step 3 without profile redirects to Step 1."""
        page.goto(f"{base_url}/step/3")
        page.wait_for_url("**/step/1", timeout=5000)
        assert "/step/1" in page.url

    def test_navigation_guard_step4(self, page, base_url):
        """Navigating directly to Step 4 without plan redirects to Step 1."""
        page.goto(f"{base_url}/step/4")
        page.wait_for_url("**/step/1", timeout=5000)
        assert "/step/1" in page.url
