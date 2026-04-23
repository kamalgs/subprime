"""Live browser smoke tests against the deployed React SPA.

These hit the real deployed URL with Playwright. They don't make LLM calls —
just validate the UI loads, routing works, static assets serve, and the
cheat-code → persona-bank flow functions end-to-end.

Run:
    SUBPRIME_URL=https://finadvisor.gkamal.online \\
    SUBPRIME_OTP_CHEAT=242424 \\
    uv run pytest product/tests/test_browser_live.py -m browser -v -s

For the full wizard-to-plan flow (mocked LLM, local uvicorn), see:
    product/tests/test_frontend_e2e.py
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

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
        host = urlparse(BASE_URL).hostname
        # Pre-dismiss the SEBI modal so every test doesn't need to click it
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
        pg = await context.new_page()
        pg.on("pageerror", lambda exc: print(f"[PAGE ERROR] {exc}"))
        pg.on(
            "console",
            lambda msg: print(f"[{msg.type}] {msg.text}") if msg.type == "error" else None,
        )
        yield pg
        await context.close()
        await browser.close()


async def _verify_cheat_in_browser(pg) -> None:
    result = await pg.evaluate(
        """async ({code}) => {
            const r = await fetch('/api/v2/session/otp/verify', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'same-origin',
                body: JSON.stringify({email: 'browsertest@example.com', code}),
            });
            return { status: r.status, body: await r.json() };
        }""",
        {"code": CHEAT},
    )
    assert result["status"] == 200, result
    assert result["body"]["is_demo"] is True, result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spa_loads_and_shows_tier_cards(page):
    await page.goto(BASE_URL + "/", wait_until="networkidle")
    await page.wait_for_selector("text=Choose your plan", timeout=10000)
    await page.wait_for_selector("text=Start free plan")
    await page.wait_for_selector("text=Most popular")


@pytest.mark.asyncio
async def test_basic_tier_navigates_to_step2(page):
    await page.goto(BASE_URL + "/", wait_until="networkidle")
    await page.click("text=Start free plan")
    await page.wait_for_url("**/step/2", timeout=10000)
    await page.wait_for_selector("text=Your investor profile")


@pytest.mark.asyncio
async def test_step2_shows_archetypes_for_regular_user(page):
    await page.goto(BASE_URL + "/step/2", wait_until="networkidle")
    await page.wait_for_selector("text=Early career", timeout=10000)
    await page.wait_for_selector("text=Mid career")
    await page.wait_for_selector("text=Retired")
    assert await page.get_by_text("Tony Stark").count() == 0


@pytest.mark.asyncio
async def test_archetype_prefills_custom_form(page):
    await page.goto(BASE_URL + "/step/2", wait_until="networkidle")
    await page.click("text=Mid career")
    age_input = page.locator("input[type='number']").first
    await age_input.wait_for(state="visible", timeout=5000)
    assert (await age_input.input_value()) == "38"


@pytest.mark.asyncio
async def test_cheat_code_unlocks_persona_bank(page):
    await page.goto(BASE_URL + "/", wait_until="networkidle")
    await _verify_cheat_in_browser(page)
    await page.goto(BASE_URL + "/step/2", wait_until="networkidle")
    await page.wait_for_selector("text=Tony Stark", timeout=10000)


@pytest.mark.asyncio
async def test_api_v2_session_endpoint(page):
    # Navigate first so fetch() has a base URL
    await page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    r = await page.evaluate("""async () => {
        const resp = await fetch('/api/v2/session', { credentials: 'same-origin' });
        return { status: resp.status, body: await resp.json() };
    }""")
    assert r["status"] == 200
    assert r["body"]["mode"] in ("basic", "premium")
    assert "id" in r["body"] and len(r["body"]["id"]) > 0


@pytest.mark.asyncio
async def test_static_assets_load(page):
    """The bundled JS + CSS that index.html references actually serve 200."""
    import re

    await page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    html = await page.evaluate("async () => (await fetch('/')).text()")
    js = re.search(r"/assets/index-[\w-]+\.js", html)
    css = re.search(r"/assets/index-[\w-]+\.css", html)
    assert js and css, "index.html did not reference Vite /assets/* paths"
    for asset in (js.group(), css.group()):
        status = await page.evaluate(
            "async (u) => (await fetch(u)).status",
            asset,
        )
        assert status == 200, f"{asset} → HTTP {status}"
