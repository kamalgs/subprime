"""Live smoke tests — run AGAINST the deployed URL after every deploy.

Two tiers:
  1. Fast/free checks (no LLM) — always run when invoked with ``-m smoke``.
     Catches ~90% of deployment regressions: missing templates, schema
     errors, broken routes, missing env vars, static-asset breakage,
     DB connectivity.

  2. LLM-hitting end-to-end checks — gated by the env var
     ``SUBPRIME_SMOKE_LLM`` (defaults to ``1`` = ON). Actually drive the
     strategy (fast) and plan (slow) LLM endpoints to validate the model
     credentials, prompt templates, and background task wiring. Expect
     ~60-120s for the full pass. Set ``SUBPRIME_SMOKE_LLM=0`` to skip
     once the app reaches steady state and LLM-call cost matters.

Run:
    SUBPRIME_URL=https://finadvisor.gkamal.online \\
    SUBPRIME_OTP_CHEAT=242424 \\
    uv run pytest product/tests/test_smoke_live.py -m smoke -v
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

pytestmark = pytest.mark.smoke

BASE_URL = os.environ.get("SUBPRIME_URL", "").rstrip("/")
CHEAT = os.environ.get("SUBPRIME_OTP_CHEAT", "242424")

# Default ON so we catch LLM regressions during this rapid-iteration phase.
# Flip to "0" / "false" / "off" once the app is stable.
_llm_env = os.environ.get("SUBPRIME_SMOKE_LLM", "1").strip().lower()
LLM_ENABLED = _llm_env not in ("0", "false", "off", "no", "")


def _require_base():
    if not BASE_URL:
        pytest.skip("SUBPRIME_URL not set — skipping live smoke tests")


def _require_llm():
    if not LLM_ENABLED:
        pytest.skip("SUBPRIME_SMOKE_LLM disabled — skipping LLM-hitting checks")


@pytest.fixture
def client():
    _require_base()
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=15.0) as c:
        yield c


@pytest.fixture
def llm_client():
    """Longer timeout — premium plan generation runs 3 perspectives + refine."""
    _require_base()
    _require_llm()
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=360.0) as c:
        yield c


def _unlock_demo_session(c: httpx.Client) -> None:
    """Walk through tier selection + OTP cheat so `c` has a demo session
    with the research persona bank available."""
    c.post("/api/select-tier", data={"mode": "basic"})
    r = c.post("/api/verify-otp", data={"email": "smoke@benji.local", "code": CHEAT})
    assert r.status_code == 200, "OTP cheat code rejected — check SUBPRIME_OTP_CHEAT"


# ---------------------------------------------------------------------------
# Basic reachability
# ---------------------------------------------------------------------------


def test_homepage_returns_html(client):
    """Root page loads and serves Benji markup."""
    r = client.get("/")
    assert r.status_code == 200
    assert "Benji" in r.text
    assert "<html" in r.text.lower()


def test_static_assets_reachable(client):
    """Key static files are served (not 404ed by a broken mount)."""
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/charts.js").status_code == 200


def test_no_service_worker_errors(client):
    r = client.get("/static/sw.js")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Step-1: tier selection (no LLM involved)
# ---------------------------------------------------------------------------


def test_step1_shows_tier_cards(client):
    r = client.get("/step/1")
    assert r.status_code == 200
    assert "Choose your plan" in r.text
    assert "Start free plan" in r.text
    assert "Premium" in r.text


def test_select_basic_tier_sets_session(client):
    r = client.post("/api/select-tier", data={"mode": "basic"})
    # HX-Redirect or 200, either way the session cookie must land
    assert r.status_code in (200, 302)
    assert "benji_session" in client.cookies


def test_step2_for_regular_user_shows_archetypes(client):
    client.post("/api/select-tier", data={"mode": "basic"})
    r = client.get("/step/2")
    assert r.status_code == 200
    # Regular (non-demo) sessions see the 3 archetype cards
    assert "Early career" in r.text
    assert "Mid career" in r.text
    assert "Retired" in r.text
    # Full research persona bank should NOT be visible here
    assert "Tony Stark" not in r.text


# ---------------------------------------------------------------------------
# Cheat-code unlock → full persona bank
# ---------------------------------------------------------------------------


def test_cheat_code_unlocks_full_persona_bank(client):
    """Submitting the cheat code should flip is_demo True and expose
    the full research persona bank on step 2."""
    client.post("/api/select-tier", data={"mode": "basic"})
    # Verify cheat code is accepted
    r = client.post(
        "/api/verify-otp",
        data={"email": "smoke-test@benji.local", "code": CHEAT},
    )
    assert r.status_code == 200, f"OTP cheat rejected (code={CHEAT!r})"

    r = client.get("/step/2")
    assert r.status_code == 200
    # Full research personas visible in demo mode
    assert "Tony Stark" in r.text or "Persona" in r.text, (
        "demo mode did not expose the full persona bank — is_demo likely "
        "not persisting across requests"
    )


# ---------------------------------------------------------------------------
# Known-good DB / ingest invariants
# ---------------------------------------------------------------------------


def test_fund_search_endpoint_doesnt_crash(client):
    """If the DuckDB schema is stale (missing launch_date etc), any
    downstream page that triggers a fund lookup will 500. We don't have
    a direct API but we can at least verify step pages respond cleanly."""
    for step in ("/step/1", "/step/2"):
        r = client.get(step)
        assert r.status_code < 500, f"{step} returned {r.status_code}"


def test_plan_status_endpoint_responds(client):
    """Polling endpoint should respond even without an active plan."""
    client.post("/api/select-tier", data={"mode": "basic"})
    r = client.get("/api/plan-status")
    assert r.status_code == 200
    data = r.json()
    assert "ready" in data
    assert data["ready"] is False


# ---------------------------------------------------------------------------
# LLM-hitting checks — gated by SUBPRIME_SMOKE_LLM (default ON)
# ---------------------------------------------------------------------------


def test_strategy_generation_against_live_llm(llm_client):
    """Drive a real strategy generation against the live advisor model.

    Validates: model credentials, prompt templates, fund universe loading,
    JSON structure of the strategy output.
    """
    _unlock_demo_session(llm_client)

    # Pick any seeded persona — demo mode has the full bank.
    r = llm_client.post("/api/select-persona", data={"persona_id": "P01"})
    assert r.status_code in (200, 302)

    # HTMX GET that fires on step 3 load — returns the strategy partial.
    r = llm_client.get("/api/generate-strategy")
    assert r.status_code == 200, f"strategy endpoint returned {r.status_code}"
    body = r.text
    # Partial should contain the key sections the template renders.
    assert "Asset allocation" in body, "strategy response missing allocation block"
    assert "Equity approach" in body, "strategy response missing equity approach"
    # No unrendered Jinja leakage
    assert "{{" not in body and "{%" not in body


def test_full_plan_generation_against_live_llm(llm_client):
    """End-to-end: tier → persona → strategy → plan. The slow one (~60-90s).

    Uses the background-task + polling flow the UI actually uses.
    """
    _unlock_demo_session(llm_client)

    r = llm_client.post("/api/select-persona", data={"persona_id": "P01"})
    assert r.status_code in (200, 302)

    # Generate strategy first (the plan request expects session.strategy set).
    r = llm_client.get("/api/generate-strategy")
    assert r.status_code == 200

    # Kick off background plan generation.
    r = llm_client.post("/api/generate-plan")
    assert r.status_code == 200
    assert r.headers.get("HX-Redirect") == "/step/4"

    # Poll plan-status until ready. Premium mode (3 perspectives + refine)
    # can take 3-5 minutes on Qwen3-235B; budget generously.
    timeout_seconds = 360
    deadline = time.time() + timeout_seconds
    status = None
    while time.time() < deadline:
        r = llm_client.get("/api/plan-status")
        assert r.status_code == 200
        status = r.json()
        if status.get("ready"):
            break
        if status.get("error"):
            pytest.fail(f"plan generation failed: {status['error']}")
        time.sleep(5)

    assert status and status.get("ready"), (
        f"plan did not become ready within {timeout_seconds}s (last status: {status})"
    )

    # /step/4 should now render the real plan (not the loading page).
    r = llm_client.get("/step/4")
    assert r.status_code == 200
    assert "Your investment plan" in r.text
    assert "Fund allocations" in r.text
    assert "Corpus projection" in r.text
    # Fallback CAGRs should ensure the returns table is always there
    assert "Bear CAGR" in r.text or "Base CAGR" in r.text
