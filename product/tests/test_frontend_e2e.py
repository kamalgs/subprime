"""End-to-end tests for the React SPA.

Starts a real uvicorn process with the production app, mocks the LLM calls,
and drives a headless Chromium through the full user flow against the built
SPA. This catches the integration bugs that purely unit tests miss:
  - SPA catch-all routing
  - React Query + background-task poll loop
  - Form submission → API → state update → navigation
  - ECharts rendering in jsdom

Run:
    make frontend                              # build the SPA first
    uv run pytest product/tests/test_frontend_e2e.py -m browser -v -s

Skipped when:
  - product/apps/web/static/dist/index.html does not exist (build not run)
  - Playwright's chromium browser isn't installed
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

_ROOT = Path(__file__).resolve().parents[1]  # product/
_DIST = _ROOT / "apps" / "web" / "static" / "dist" / "index.html"


def _require_spa_build():
    if not _DIST.exists():
        pytest.skip("SPA build missing — run `make frontend` first")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------


def _mock_strategy():
    from subprime.core.models import StrategyOutline

    return StrategyOutline(
        equity_pct=70,
        debt_pct=20,
        gold_pct=10,
        other_pct=0,
        equity_approach="Balanced index-heavy mix",
        key_themes=["growth tilt", "low cost"],
        risk_return_summary="Expected 11% CAGR with moderate drawdowns",
        open_questions=[],
    )


def _mock_plan():
    from subprime.core.models import Allocation, InvestmentPlan, MutualFund

    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(
                    amfi_code="119551",
                    name="UTI Nifty 50 Index Fund",
                    category="Large Cap",
                    fund_house="UTI",
                    expense_ratio=0.18,
                ),
                allocation_pct=60,
                mode="sip",
                monthly_sip_inr=15000,
                rationale="Low-cost core equity exposure.",
            ),
            Allocation(
                fund=MutualFund(
                    amfi_code="112090",
                    name="Axis Bluechip Fund",
                    category="Large Cap",
                    fund_house="Axis",
                    expense_ratio=0.55,
                ),
                allocation_pct=40,
                mode="sip",
                monthly_sip_inr=10000,
                rationale="Active large-cap complement.",
            ),
        ],
        projected_returns={"bear": 8.0, "base": 12.0, "bull": 16.0},
        rationale="A simple two-fund portfolio for long-term growth.",
        risks=["Market volatility."],
    )


# ---------------------------------------------------------------------------
# Server fixture — real uvicorn, mocked LLM
# ---------------------------------------------------------------------------


@pytest.fixture
def live_server(tmp_path):
    """Start a real uvicorn subprocess with mocked LLM calls. Returns the URL."""
    _require_spa_build()
    import os

    port = _free_port()

    # Inject mocks into the child process via a bootstrap script that replaces
    # the LLM-call functions on import.
    bootstrap = tmp_path / "bootstrap.py"
    bootstrap.write_text(
        """
import os, asyncio
from unittest.mock import patch, AsyncMock
from pydantic_ai.usage import RunUsage
from subprime.core.models import (
    Allocation, InvestmentPlan, MutualFund, StrategyOutline,
)


def _strategy():
    return StrategyOutline(
        equity_pct=70, debt_pct=20, gold_pct=10, other_pct=0,
        equity_approach="Balanced index-heavy mix",
        key_themes=["growth tilt", "low cost"],
        risk_return_summary="Expected 11% CAGR with moderate drawdowns",
        open_questions=[],
    )


def _plan():
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(amfi_code="119551", name="UTI Nifty 50 Index Fund",
                                category="Large Cap", fund_house="UTI", expense_ratio=0.18),
                allocation_pct=60, mode="sip", monthly_sip_inr=15000,
                rationale="Low-cost core equity exposure.",
            ),
            Allocation(
                fund=MutualFund(amfi_code="112090", name="Axis Bluechip Fund",
                                category="Large Cap", fund_house="Axis", expense_ratio=0.55),
                allocation_pct=40, mode="sip", monthly_sip_inr=10000,
                rationale="Active large-cap complement.",
            ),
        ],
        projected_returns={"bear": 8.0, "base": 12.0, "bull": 16.0},
        rationale="A simple two-fund portfolio.",
        risks=["Market volatility."],
    )


async def _strategy_mock(*args, **kwargs):
    return _strategy(), RunUsage()


async def _plan_mock(*args, **kwargs):
    # Mirror the real staged contract: fire on_partial for every stage so
    # the web layer saves partial plan + stages_done to session state as
    # the production code does.
    cb = kwargs.get("on_partial")
    plan_val = _plan()
    if cb is not None:
        await cb(plan_val, ["core"])
        await cb(plan_val, ["core", "risks"])
        await cb(plan_val, ["core", "risks", "setup"])
    return plan_val, RunUsage()


# Patch at the import-site BEFORE uvicorn starts
import apps.web.api_v2.strategy as _sm
import apps.web.api_v2.plan as _pm
_sm.generate_strategy = _strategy_mock
_pm.generate_plan_staged = _plan_mock

import uvicorn
uvicorn.run(
    "apps.web.main:create_app",
    factory=True, host="127.0.0.1", port="""
        + str(port)
        + """,
    log_level="warning",
)
"""
    )

    env = dict(os.environ)
    env["SUBPRIME_OTP_CHEAT"] = "123456"
    # Prevent the lifespan from trying to connect to Postgres during the test
    env.pop("DATABASE_URL", None)
    # The subprocess doesn't inherit pytest's pythonpath. Add both src and
    # product roots so `apps.web.*` and `subprime.*` imports resolve.
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [
                str(_ROOT / "src"),
                str(_ROOT),  # so apps/ is importable
                existing,
            ],
        )
    )

    proc = subprocess.Popen(
        [sys.executable, str(bootstrap)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    url = f"http://127.0.0.1:{port}"
    # Wait up to 30s — startup runs schema migration + universe cache warming
    import httpx

    deadline = time.time() + 30
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            # Process already exited — crashed on startup
            out, err = proc.communicate(timeout=2)
            pytest.fail(
                f"Server crashed at startup:\nSTDOUT:\n{out.decode()[-1500:]}\nSTDERR:\n{err.decode()[-2500:]}"
            )
        try:
            r = httpx.get(url + "/api/v2/session", timeout=1.0)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            time.sleep(0.3)
    if not ready:
        proc.terminate()
        out, err = proc.communicate(timeout=5)
        pytest.fail(
            f"Server never accepted connections:\nSTDOUT:\n{out.decode()[-1500:]}\nSTDERR:\n{err.decode()[-2500:]}"
        )

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------
# Playwright fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def page(live_server):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("playwright not installed")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium browser not available: {exc}")
        context = await browser.new_context()
        # Pre-dismiss the SEBI modal so tests don't have to click through it
        from urllib.parse import urlparse

        host = urlparse(live_server).hostname
        await context.add_cookies(
            [
                {
                    "name": "sebi_ack",
                    "value": "1",
                    "domain": host,
                    "path": "/",
                }
            ]
        )
        page = await context.new_page()
        page.on("pageerror", lambda exc: print(f"[PAGE ERROR] {exc}"))
        page.on(
            "console",
            lambda msg: print(f"[{msg.type}] {msg.text}") if msg.type == "error" else None,
        )
        yield (page, live_server)
        await context.close()
        await browser.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spa_loads_at_root(page):
    """Navigating to / should serve the SPA and render the tier page."""
    p, url = page
    await p.goto(url + "/", wait_until="networkidle")
    html = await p.content()
    print(f"\n=== PAGE HTML @ {p.url} ===\n{html[:1500]}\n=== END ===")
    await p.wait_for_selector("text=Choose your plan", timeout=5000)
    await p.wait_for_selector("text=Start free plan")
    await p.wait_for_selector("text=Most popular")


@pytest.mark.asyncio
async def test_step1_basic_navigates_to_step2(page):
    p, url = page
    await p.goto(url + "/", wait_until="networkidle")
    await p.click("text=Start free plan")
    await p.wait_for_selector("text=Your investor profile", timeout=5000)
    # Regular user sees 3 archetype cards
    await p.wait_for_selector("text=Early career")
    await p.wait_for_selector("text=Mid career")
    await p.wait_for_selector("text=Retired")


@pytest.mark.asyncio
async def test_archetype_prefills_custom_form(page):
    p, url = page
    await p.goto(url + "/step/2", wait_until="networkidle")
    await p.click("text=Mid career")
    # After clicking, we should be on Custom tab with prefilled values
    await p.wait_for_selector("input[type='number']", timeout=2000)
    # Age input should be 38 (mid_career archetype)
    age_input = p.locator("input[type='number']").first
    age = await age_input.input_value()
    assert age == "38", f"expected age=38 from mid-career archetype, got {age!r}"


@pytest.mark.asyncio
async def test_full_wizard_flow(page):
    """End-to-end: tier → archetype → custom form → strategy → plan → result."""
    p, url = page
    await p.goto(url + "/", wait_until="networkidle")

    # Step 1: basic tier
    await p.click("text=Start free plan")
    await p.wait_for_selector("text=Your investor profile")

    # Step 2: pick mid-career archetype, fill name, save, then continue
    await p.click("text=Mid career")
    await p.locator('input[placeholder="e.g. Ravi Kumar"]').fill("Test User")
    await p.click("text=Save profile")
    await p.click("text=Build my plan")

    # Step 3: strategy (mocked) renders
    await p.wait_for_selector("text=Asset allocation", timeout=10000)
    await p.wait_for_selector("text=Balanced index-heavy mix")

    # Click Generate my plan → navigates to /step/4
    await p.click("text=Generate my plan")
    await p.wait_for_url("**/step/4", timeout=5000)

    # Loading page appears; poll for plan ready
    await p.wait_for_selector("text=Building your plan", timeout=3000)

    # Once plan is ready, the final result renders
    await p.wait_for_selector("text=Your investment plan", timeout=30000)
    await p.wait_for_selector("text=UTI Nifty 50 Index Fund")
    await p.wait_for_selector("text=Corpus projection")
    await p.wait_for_selector("text=Fund allocations")


@pytest.mark.asyncio
async def test_cheat_code_unlocks_persona_bank(page):
    """Direct API call to verify the cheat code, then confirm the UI reflects it.

    The 'Send code' UX step requires SMTP + a Postgres pool (neither set up in
    this test). We exercise the backend path via page.request and verify the
    frontend picks up the is_demo flag when it loads /step/2.
    """
    p, url = page
    # Cookie from the live_server fixture already carries sebi_ack; get a real session cookie too
    await p.goto(url + "/", wait_until="networkidle")

    # Hit the verify endpoint directly from the browser context so the session
    # cookie the server sets is captured.
    # Fire the verify from inside the browser so the session cookie is set
    # on the same context as our page navigation.
    body = await p.evaluate("""
        async () => {
            const r = await fetch('/api/v2/session/otp/verify', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'same-origin',
                body: JSON.stringify({email: 'tester@example.com', code: '123456'}),
            });
            return { status: r.status, body: await r.json() };
        }
    """)
    assert body["status"] == 200, body
    assert body["body"]["verified"] is True and body["body"]["is_demo"] is True

    await p.goto(url + "/step/2", wait_until="networkidle")
    await p.wait_for_selector("text=Tony Stark", timeout=5000)
