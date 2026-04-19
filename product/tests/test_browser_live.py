"""Live browser smoke tests — full Playwright run against the deployed URL.

These are the *real* smoke tests: they drive a headless Chromium through the
actual user flow the way a human would, which means they catch the JS wiring
bugs that plain HTTP smoke tests can't.

Run:
    SUBPRIME_URL=https://finadvisor.gkamal.online \\
    SUBPRIME_OTP_CHEAT=242424 \\
    uv run pytest product/tests/test_browser_live.py -m browser -v -s

Marker `browser` is deselected by default.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.browser

BASE_URL = os.environ.get("SUBPRIME_URL", "").rstrip("/")
CHEAT = os.environ.get("SUBPRIME_OTP_CHEAT", "242424")


def _require_base():
    if not BASE_URL:
        pytest.skip("SUBPRIME_URL not set")


@pytest.fixture
async def page():
    _require_base()
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        # Surface console errors in the pytest report
        page.on("pageerror", lambda exc: print(f"[PAGE ERROR] {exc}"))
        page.on("console", lambda msg: print(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        yield page
        await context.close()
        await browser.close()


async def _dismiss_sebi(page) -> None:
    """Wait for the SEBI modal (which appears after JS runs, not immediately
    on DOM load) and dismiss it. Safe to call if modal never shows."""
    modal = page.locator("#sebi-modal")
    try:
        await modal.wait_for(state="visible", timeout=2000)
        await page.locator("#sebi-ack").click()
        await modal.wait_for(state="hidden", timeout=3000)
    except Exception:
        pass  # cookie may already be set or modal not rendered


async def _unlock_demo(page) -> None:
    """Walk through step 1 using the OTP cheat code so we land on step 2 with
    the full research persona bank available."""
    await page.goto(f"{BASE_URL}/step/1", wait_until="domcontentloaded")
    await _dismiss_sebi(page)
    # Fill premium email + request OTP
    await page.get_by_placeholder("your@email.com").fill("browser-test@benji.local")
    await page.get_by_role("button", name=re.compile("Send code", re.I)).click()
    # OTP input appears — submit the cheat code
    code_input = page.locator('input[name="code"]')
    await code_input.wait_for(timeout=10000)
    await code_input.fill(CHEAT)
    await page.get_by_role("button", name=re.compile("Verify", re.I)).click()
    # Wait for redirect to step 2
    await page.wait_for_url(re.compile(r"/step/2"), timeout=15000)


# ---------------------------------------------------------------------------
# Actual browser checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step1_renders_and_sebi_modal_shows(page):
    await page.goto(f"{BASE_URL}/step/1", wait_until="domcontentloaded")
    await page.wait_for_selector("text=Choose your plan", timeout=10000)
    # Modal visible on first visit
    assert await page.locator("#sebi-modal").is_visible()


@pytest.mark.asyncio
async def test_regular_user_sees_archetypes(page):
    await page.goto(f"{BASE_URL}/step/1", wait_until="domcontentloaded")
    await _dismiss_sebi(page)
    # Basic tier → step 2
    await page.get_by_role("button", name=re.compile("Start free plan", re.I)).click()
    await page.wait_for_url(re.compile(r"/step/2"), timeout=10000)
    await page.wait_for_selector("text=Early career", timeout=5000)
    assert not await page.locator("text=Tony Stark").is_visible()


@pytest.mark.asyncio
async def test_cheat_code_shows_full_persona_bank(page):
    await _unlock_demo(page)
    await page.wait_for_selector("text=Tony Stark", timeout=5000)


@pytest.mark.asyncio
async def test_full_flow_strategy_to_plan(page):
    """The actual user journey: cheat → persona → strategy → Generate Plan
    → loading page → reveal overlay → plan visible.

    Catches: broken JS wiring, generate-plan button not firing, loading-page
    redirect hang, stale plan_generating flag.
    """
    await _unlock_demo(page)

    # Pick a persona — the first card in the demo grid
    await page.wait_for_selector("text=Tony Stark", timeout=10000)
    await page.get_by_text("Tony Stark").first.click()
    # Persona selection uses hx-swap=none + HX-Redirect to /step/3
    await page.wait_for_url(re.compile(r"/step/3"), timeout=15000)

    # Strategy is generated on load — wait for it to render
    await page.wait_for_selector("text=Asset allocation", timeout=90000)

    # Click Generate my plan
    btn = page.locator("#generate-plan-btn")
    await btn.wait_for(state="visible", timeout=5000)
    assert not await btn.is_disabled(), "Generate plan button was pre-disabled"

    # Listen for the POST to confirm the click fired the request
    plan_request_seen = {"value": False}

    def on_request(request):
        if request.method == "POST" and "/api/generate-plan" in request.url:
            plan_request_seen["value"] = True

    page.on("request", on_request)
    await btn.click()

    # Either we move to /step/4 (HX-Redirect) or the button shows progress
    await page.wait_for_url(re.compile(r"/step/4"), timeout=15000)

    assert plan_request_seen["value"], "Clicking Generate Plan did not POST /api/generate-plan"

    # Loading page should render
    await page.wait_for_selector("text=Building your plan", timeout=5000)

    # Wait for the final plan to render. The loading page polls /api/plan-status
    # and navigates to /step/4 when ready; step 4 shows 'Fund allocations'.
    # Budget generously — basic plan on Qwen3-235B runs ~50-90s.
    try:
        await page.wait_for_selector("text=Fund allocations", timeout=180000)
    except Exception:
        url = page.url
        body_text = (await page.locator("body").text_content() or "")[:400]
        print(f"\n[DIAG] url={url}")
        print(f"[DIAG] first-400-chars: {body_text}")
        await page.screenshot(path="/tmp/plan-timeout.png", full_page=True)
        print("[DIAG] screenshot saved to /tmp/plan-timeout.png")
        raise

    await page.wait_for_selector("text=Corpus projection", timeout=2000)


@pytest.mark.asyncio
async def test_generate_plan_works_after_back_navigation(page):
    """Simulates the 'step 4 interrupted → back to step 3 → click again' case.

    Ensures the button remains wired after HTMX re-swaps and after a full
    page navigation + back.
    """
    await _unlock_demo(page)
    await page.wait_for_selector("text=Tony Stark", timeout=10000)
    await page.get_by_text("Tony Stark").first.click()
    await page.wait_for_url(re.compile(r"/step/3"), timeout=15000)
    await page.wait_for_selector("text=Asset allocation", timeout=90000)

    # First click — fires request and navigates
    await page.locator("#generate-plan-btn").click()
    await page.wait_for_url(re.compile(r"/step/4"), timeout=15000)

    # Now navigate back to /step/3 (simulates user hitting back or the
    # 'Back to strategy' link on an error state).
    await page.goto(f"{BASE_URL}/step/3", wait_until="domcontentloaded")
    await page.wait_for_selector("text=Asset allocation", timeout=90000)

    # Click must still fire a request
    plan_request_seen = {"value": False}
    page.on("request", lambda r: plan_request_seen.__setitem__("value", True) if "/api/generate-plan" in r.url and r.method == "POST" else None)
    await page.locator("#generate-plan-btn").click()
    await page.wait_for_url(re.compile(r"/step/4"), timeout=15000)
    assert plan_request_seen["value"], "Generate Plan button lost its handler after back-navigation"
