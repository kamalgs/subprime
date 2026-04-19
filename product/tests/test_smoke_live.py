"""Live smoke tests — run AGAINST the deployed URL after every deploy.

These tests hit the real web app over HTTP. They do NOT call the LLM endpoints
(generate-plan, revise-strategy, generate-strategy) — so they're fast, free, and
catch 90% of deployment regressions: missing templates, schema errors, broken
routes, missing env vars, static-asset breakage, DB connectivity.

Run:
    SUBPRIME_URL=https://finadvisor.gkamal.online \\
    SUBPRIME_OTP_CHEAT=242424 \\
    uv run pytest product/tests/test_smoke_live.py -m smoke -v

By default these tests are DESELECTED (marked `smoke`) so they never run in CI
or local pytest. Invoke explicitly with `-m smoke`.
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.smoke

BASE_URL = os.environ.get("SUBPRIME_URL", "").rstrip("/")
CHEAT = os.environ.get("SUBPRIME_OTP_CHEAT", "242424")


def _require_base():
    if not BASE_URL:
        pytest.skip("SUBPRIME_URL not set — skipping live smoke tests")


@pytest.fixture
def client():
    _require_base()
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=15.0) as c:
        yield c


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
