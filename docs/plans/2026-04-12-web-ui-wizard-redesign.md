# FinAdvisor Web UI Wizard Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Gradio chat interface with a multi-step wizard (FastAPI + Jinja2 + HTMX + Tailwind CSS) that separates basic/premium tier selection, uses form widgets for structured input, and gives LLM commentary dedicated rendered content areas.

**Architecture:** FastAPI serves Jinja2 templates with HTMX for partial page swaps. Four wizard steps: tier selection → profile form → strategy dashboard with chat feedback → rich plan results. Session state managed via an abstract SessionStore protocol with an in-memory implementation. All existing `subprime` package code untouched — the web app imports the same functions.

**Tech Stack:** FastAPI, Jinja2, HTMX (CDN), Tailwind CSS (CDN), Chart.js (CDN), uvicorn, python-multipart, markdown

---

## File Map

| File | Responsibility | Task |
|---|---|---|
| `apps/web/session.py` | Session/SessionSummary models, SessionStore protocol, InMemorySessionStore | Task 1 |
| `apps/web/rendering.py` | INR formatting, markdown→HTML, chart data helpers | Task 2 |
| `apps/web/main.py` | FastAPI app factory, middleware, static/template mount, session dependency | Task 3 |
| `apps/web/routes.py` | Page routes: GET /, /step/1-4 | Task 4 |
| `apps/web/api.py` | HTMX API endpoints: POST /api/* | Task 5 |
| `apps/web/templates/base.html` | Layout shell: CDN links, nav, step indicator, content block | Task 3 |
| `apps/web/templates/step_plan.html` | Step 1: Basic vs Premium cards | Task 4 |
| `apps/web/templates/step_profile.html` | Step 2: Persona cards + custom form | Task 4 |
| `apps/web/templates/step_strategy.html` | Step 3: Strategy dashboard + chat | Task 5 |
| `apps/web/templates/step_result.html` | Step 4: Full plan results | Task 6 |
| `apps/web/templates/partials/*.html` | HTMX swap targets for async operations | Tasks 5-6 |
| `apps/web/static/app.css` | Custom styles beyond Tailwind | Task 3 |
| `apps/web/static/charts.js` | Chart.js donut + bar chart helpers | Task 6 |
| `apps/web/gradio_app.py` | Renamed from app.py (preserved) | Task 7 |
| `pyproject.toml` | Dependency updates | Task 7 |
| `Dockerfile` | Updated entrypoint | Task 7 |
| `src/subprime/cli.py:355-381` | web command → uvicorn | Task 7 |
| `tests/test_web_wizard.py` | All tests for the new web app | Tasks 1-7 |

---

### Task 1: Session Store

**Files:**
- Create: `apps/web/session.py`
- Create: `tests/test_web_wizard.py`

- [ ] **Step 1: Write the failing tests for Session model and InMemorySessionStore**

```python
# tests/test_web_wizard.py
"""Tests for the FinAdvisor wizard web app."""

from __future__ import annotations

import pytest

from apps.web.session import InMemorySessionStore, Session, SessionSummary


class TestSessionModel:
    def test_create_session_defaults(self):
        s = Session()
        assert s.current_step == 1
        assert s.mode == "basic"
        assert s.profile is None
        assert s.strategy is None
        assert s.plan is None
        assert s.strategy_chat == []
        assert s.id  # UUID generated
        assert s.created_at
        assert s.updated_at

    def test_create_session_premium(self):
        s = Session(mode="premium")
        assert s.mode == "premium"

    def test_to_summary(self):
        s = Session()
        summary = s.to_summary()
        assert isinstance(summary, SessionSummary)
        assert summary.id == s.id
        assert summary.current_step == 1
        assert summary.investor_name is None

    def test_to_summary_with_profile(self):
        from subprime.core.models import InvestorProfile

        profile = InvestorProfile(
            id="test",
            name="Test User",
            age=30,
            risk_appetite="moderate",
            investment_horizon_years=10,
            monthly_investible_surplus_inr=50000,
            existing_corpus_inr=0,
            liabilities_inr=0,
            financial_goals=["retirement"],
            life_stage="early career",
            tax_bracket="new_regime",
        )
        s = Session(profile=profile, current_step=3)
        summary = s.to_summary()
        assert summary.investor_name == "Test User"
        assert summary.current_step == 3


class TestInMemorySessionStore:
    @pytest.fixture
    def store(self):
        return InMemorySessionStore()

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        result = await store.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_and_get(self, store):
        session = Session()
        await store.save(session)
        retrieved = await store.get(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, store):
        session = Session()
        await store.save(session)
        session.current_step = 3
        session.mode = "premium"
        await store.save(session)
        retrieved = await store.get(session.id)
        assert retrieved.current_step == 3
        assert retrieved.mode == "premium"

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, store):
        result = await store.list_sessions()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_sessions(self, store):
        s1 = Session()
        s2 = Session(mode="premium")
        await store.save(s1)
        await store.save(s2)
        result = await store.list_sessions()
        assert len(result) == 2
        assert all(isinstance(r, SessionSummary) for r in result)

    @pytest.mark.asyncio
    async def test_list_sessions_limit(self, store):
        for _ in range(5):
            await store.save(Session())
        result = await store.list_sessions(limit=3)
        assert len(result) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.web.session'`

- [ ] **Step 3: Implement session.py**

```python
# apps/web/session.py
"""Session management for the FinAdvisor wizard.

Provides a SessionStore protocol and an in-memory implementation.
The protocol is designed so a DuckDB/SQLite/Redis backend can be
swapped in without changing routes or API code.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from subprime.core.models import (
    ConversationTurn,
    InvestmentPlan,
    InvestorProfile,
    StrategyOutline,
)


class SessionSummary(BaseModel):
    """Lightweight session info for listing."""

    id: str
    investor_name: str | None = None
    mode: str = "basic"
    current_step: int = 1
    created_at: datetime
    updated_at: datetime


class Session(BaseModel):
    """Full wizard session state."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_step: int = 1
    mode: Literal["basic", "premium"] = "basic"
    profile: InvestorProfile | None = None
    strategy: StrategyOutline | None = None
    plan: InvestmentPlan | None = None
    strategy_chat: list[ConversationTurn] = []

    def to_summary(self) -> SessionSummary:
        return SessionSummary(
            id=self.id,
            investor_name=self.profile.name if self.profile else None,
            mode=self.mode,
            current_step=self.current_step,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class SessionStore(Protocol):
    async def get(self, session_id: str) -> Session | None: ...
    async def save(self, session: Session) -> None: ...
    async def list_sessions(self, limit: int = 20) -> list[SessionSummary]: ...


class InMemorySessionStore:
    """Dict-backed session store. Suitable for single-process dev/demo use."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    async def save(self, session: Session) -> None:
        session.updated_at = datetime.now(timezone.utc)
        self._sessions[session.id] = session

    async def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True,
        )
        return [s.to_summary() for s in sessions[:limit]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/session.py tests/test_web_wizard.py
git commit -m "feat(web): add session store protocol and in-memory implementation"
```

---

### Task 2: Rendering Helpers

**Files:**
- Create: `apps/web/rendering.py`
- Modify: `tests/test_web_wizard.py`

- [ ] **Step 1: Write the failing tests for rendering helpers**

Append to `tests/test_web_wizard.py`:

```python
from apps.web.rendering import format_inr, render_markdown, compute_corpus, inflation_adjusted


class TestFormatInr:
    def test_crores(self):
        assert format_inr(2_50_00_000) == "₹2.50 Cr"

    def test_lakhs(self):
        assert format_inr(5_50_000) == "₹5.50 L"

    def test_small_amount(self):
        assert format_inr(45000) == "₹45,000"

    def test_one_crore(self):
        assert format_inr(1_00_00_000) == "₹1.00 Cr"

    def test_one_lakh(self):
        assert format_inr(1_00_000) == "₹1.00 L"

    def test_zero(self):
        assert format_inr(0) == "₹0"


class TestRenderMarkdown:
    def test_bold(self):
        result = render_markdown("This is **bold** text")
        assert "<strong>bold</strong>" in result

    def test_bullet_list(self):
        result = render_markdown("- item one\n- item two")
        assert "<li>" in result

    def test_paragraphs(self):
        result = render_markdown("First para\n\nSecond para")
        assert "<p>" in result

    def test_empty_string(self):
        assert render_markdown("") == ""

    def test_html_escaping(self):
        result = render_markdown("Use <script>alert(1)</script>")
        assert "<script>" not in result


class TestComputeCorpus:
    def test_basic_computation(self):
        result = compute_corpus(10000, 10, 12.0)
        assert result > 0
        # 10k/month at 12% for 10 years ≈ 23.2L
        assert 22_00_000 < result < 24_00_000

    def test_zero_sip(self):
        assert compute_corpus(0, 10, 12.0) == 0.0

    def test_zero_years(self):
        assert compute_corpus(10000, 0, 12.0) == 0.0

    def test_zero_cagr(self):
        assert compute_corpus(10000, 10, 0) == 0.0


class TestInflationAdjusted:
    def test_basic_discount(self):
        result = inflation_adjusted(100_00_000, 10)
        # 1Cr discounted 10yr at 6% ≈ 55.8L
        assert 55_00_000 < result < 57_00_000

    def test_zero_years(self):
        assert inflation_adjusted(100_00_000, 0) == 100_00_000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py::TestFormatInr -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.web.rendering'`

- [ ] **Step 3: Implement rendering.py**

```python
# apps/web/rendering.py
"""HTML rendering helpers for the FinAdvisor wizard.

INR formatting (lakhs/crores), markdown-to-HTML, corpus projection math.
"""

from __future__ import annotations

import html as html_mod
import markdown as md


def format_inr(amount: float) -> str:
    """Format INR in lakhs/crores. Never uses millions."""
    if amount >= 1_00_00_000:
        return f"\u20b9{amount / 1_00_00_000:.2f} Cr"
    elif amount >= 1_00_000:
        return f"\u20b9{amount / 1_00_000:.2f} L"
    elif amount > 0:
        return f"\u20b9{amount:,.0f}"
    return "\u20b90"


def render_markdown(text: str) -> str:
    """Convert markdown text to safe HTML. Used for model commentary."""
    if not text:
        return ""
    return md.markdown(text, extensions=["sane_lists"])


def compute_corpus(monthly_sip: float, years: int, cagr_pct: float) -> float:
    """Compute future value of monthly SIP at given CAGR."""
    if cagr_pct <= 0 or monthly_sip <= 0 or years <= 0:
        return 0.0
    r = cagr_pct / 100 / 12
    n = years * 12
    return monthly_sip * (((1 + r) ** n - 1) / r) * (1 + r)


def inflation_adjusted(future_value: float, years: int, inflation_pct: float = 6.0) -> float:
    """Discount future value to today's terms."""
    if years <= 0:
        return future_value
    return future_value / ((1 + inflation_pct / 100) ** years)


def chart_data_donut(equity: float, debt: float, gold: float, other: float) -> dict:
    """Return Chart.js-ready data dict for asset allocation donut."""
    labels = []
    values = []
    colors = []
    color_map = {
        "Equity": "#4f46e5",
        "Debt": "#0891b2",
        "Gold": "#d97706",
        "Other": "#6b7280",
    }
    for label, val in [("Equity", equity), ("Debt", debt), ("Gold", gold), ("Other", other)]:
        if val > 0:
            labels.append(label)
            values.append(round(val, 1))
            colors.append(color_map[label])
    return {"labels": labels, "values": values, "colors": colors}


def chart_data_corpus(
    monthly_sip: float, years: int, bear: float, base: float, bull: float,
) -> dict:
    """Return Chart.js-ready data for corpus projection bar chart."""
    scenarios = []
    for label, cagr, color in [
        ("Bear", bear, "#ef4444"),
        ("Base", base, "#f59e0b"),
        ("Bull", bull, "#22c55e"),
    ]:
        if cagr > 0:
            fv = compute_corpus(monthly_sip, years, cagr)
            pv = inflation_adjusted(fv, years)
            scenarios.append({
                "label": label,
                "cagr": round(cagr, 1),
                "future_value": round(fv),
                "present_value": round(pv),
                "future_value_fmt": format_inr(fv),
                "present_value_fmt": format_inr(pv),
                "color": color,
            })
    return {"scenarios": scenarios, "sip_fmt": format_inr(monthly_sip), "years": years}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/rendering.py tests/test_web_wizard.py
git commit -m "feat(web): add rendering helpers — INR formatting, markdown, chart data"
```

---

### Task 3: FastAPI App Shell + Base Template

**Files:**
- Create: `apps/web/main.py`
- Create: `apps/web/templates/base.html`
- Create: `apps/web/static/app.css`
- Modify: `tests/test_web_wizard.py`

- [ ] **Step 1: Write the failing tests for the FastAPI app**

Append to `tests/test_web_wizard.py`:

```python
from httpx import ASGITransport, AsyncClient


class TestAppFactory:
    def test_create_app(self):
        from apps.web.main import create_app

        app = create_app()
        assert app is not None

    @pytest.mark.asyncio
    async def test_root_redirects_to_step1(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/", follow_redirects=False)
            assert resp.status_code == 307
            assert resp.headers["location"] == "/step/1"

    @pytest.mark.asyncio
    async def test_static_files_served(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/static/app.css")
            assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py::TestAppFactory -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.web.main'`

- [ ] **Step 3: Create base.html template**

```html
<!-- apps/web/templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}FinAdvisor{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="/static/app.css">
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        primary: { 50: '#eef2ff', 100: '#e0e7ff', 500: '#6366f1', 600: '#4f46e5', 700: '#4338ca' },
                        bear: '#ef4444',
                        base: '#f59e0b',
                        bull: '#22c55e',
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-gray-50 text-slate-700 min-h-screen">

    <!-- Header -->
    <header class="bg-white border-b border-gray-200">
        <div class="max-w-4xl mx-auto px-4 py-4">
            <div class="text-center">
                <h1 class="text-2xl font-bold text-slate-900">FinAdvisor</h1>
                <p class="text-sm text-slate-500 mt-1">AI-powered mutual fund advisory for Indian investors</p>
            </div>
            <p class="text-xs text-red-600 text-center mt-2">
                ⚠ For educational and research purposes only. Not SEBI-registered investment advice.
                Please consult a certified financial advisor before making investment decisions.
            </p>
        </div>
    </header>

    <!-- Step Indicator -->
    {% if current_step is defined and current_step >= 1 %}
    <nav class="max-w-4xl mx-auto px-4 py-6">
        <ol class="flex items-center w-full">
            {% set steps = [
                (1, "Choose Plan"),
                (2, "Your Profile"),
                (3, "Strategy"),
                (4, "Your Plan")
            ] %}
            {% for num, label in steps %}
            <li class="flex items-center {% if not loop.last %}w-full{% endif %}">
                <div class="flex items-center">
                    {% if num < current_step %}
                    <span class="flex items-center justify-center w-8 h-8 rounded-full bg-primary-600 text-white text-sm font-bold shrink-0">
                        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path></svg>
                    </span>
                    {% elif num == current_step %}
                    <span class="flex items-center justify-center w-8 h-8 rounded-full bg-primary-600 text-white text-sm font-bold shrink-0">{{ num }}</span>
                    {% else %}
                    <span class="flex items-center justify-center w-8 h-8 rounded-full border-2 border-gray-300 text-gray-400 text-sm font-bold shrink-0">{{ num }}</span>
                    {% endif %}
                    <span class="ml-2 text-sm font-medium {% if num <= current_step %}text-slate-900{% else %}text-gray-400{% endif %} whitespace-nowrap">{{ label }}</span>
                </div>
                {% if not loop.last %}
                <div class="w-full h-0.5 mx-4 {% if num < current_step %}bg-primary-600{% else %}bg-gray-200{% endif %}"></div>
                {% endif %}
            </li>
            {% endfor %}
        </ol>
    </nav>
    {% endif %}

    <!-- Content -->
    <main class="max-w-4xl mx-auto px-4 pb-12">
        {% block content %}{% endblock %}
    </main>

    <!-- Footer -->
    <footer class="border-t border-gray-200 mt-auto">
        <div class="max-w-4xl mx-auto px-4 py-4 text-center text-xs text-slate-400">
            FinAdvisor — part of the <a href="#" class="underline">Subprime</a> research project
        </div>
    </footer>

    {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 4: Create app.css**

```css
/* apps/web/static/app.css */

/* HTMX loading indicator */
.htmx-indicator {
    display: none;
}
.htmx-request .htmx-indicator,
.htmx-request.htmx-indicator {
    display: inline-block;
}

/* Skeleton loading animation */
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
.skeleton {
    animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    background-color: #e5e7eb;
    border-radius: 0.375rem;
}

/* Markdown rendered content */
.prose-commentary p { margin-bottom: 0.75rem; }
.prose-commentary ul { list-style-type: disc; padding-left: 1.5rem; margin-bottom: 0.75rem; }
.prose-commentary ol { list-style-type: decimal; padding-left: 1.5rem; margin-bottom: 0.75rem; }
.prose-commentary li { margin-bottom: 0.25rem; }
.prose-commentary strong { font-weight: 600; }

/* Star ratings */
.stars { color: #d97706; letter-spacing: 1px; }

/* Smooth transitions for HTMX swaps */
.fade-in {
    animation: fadeIn 0.3s ease-in;
}
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 5: Implement main.py**

```python
# apps/web/main.py
"""FastAPI application factory for the FinAdvisor wizard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from apps.web.session import InMemorySessionStore, Session

_APP_DIR = Path(__file__).parent
_TEMPLATES_DIR = _APP_DIR / "templates"
_STATIC_DIR = _APP_DIR / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="FinAdvisor")

    # Session store — swap implementation here for persistence
    store = InMemorySessionStore()
    app.state.session_store = store

    # Templates and static files
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Root redirect
    @app.get("/")
    async def root():
        return RedirectResponse(url="/step/1", status_code=307)

    # Import and include routers
    from apps.web.routes import router as page_router
    from apps.web.api import router as api_router

    app.include_router(page_router)
    app.include_router(api_router)

    return app
```

- [ ] **Step 6: Create stub routes.py and api.py so the app can import**

```python
# apps/web/routes.py
"""Page routes for the FinAdvisor wizard steps."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
```

```python
# apps/web/api.py
"""HTMX API endpoints for the FinAdvisor wizard."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py::TestAppFactory -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add apps/web/main.py apps/web/routes.py apps/web/api.py apps/web/templates/base.html apps/web/static/app.css tests/test_web_wizard.py
git commit -m "feat(web): FastAPI app shell with base template, step indicator, static files"
```

---

### Task 4: Step 1 (Tier Selection) + Step 2 (Profile) Pages

**Files:**
- Create: `apps/web/templates/step_plan.html`
- Create: `apps/web/templates/step_profile.html`
- Create: `apps/web/templates/partials/persona_card.html`
- Modify: `apps/web/routes.py`
- Modify: `apps/web/api.py`
- Modify: `tests/test_web_wizard.py`

- [ ] **Step 1: Write the failing tests for step 1 and step 2 routes**

Append to `tests/test_web_wizard.py`:

```python
class TestStep1TierSelection:
    @pytest.mark.asyncio
    async def test_step1_renders(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/step/1")
            assert resp.status_code == 200
            assert "Basic" in resp.text
            assert "Premium" in resp.text

    @pytest.mark.asyncio
    async def test_select_tier_basic(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/select-tier",
                data={"mode": "basic"},
                follow_redirects=False,
            )
            assert resp.status_code == 200
            assert resp.headers.get("hx-redirect") == "/step/2"

    @pytest.mark.asyncio
    async def test_select_tier_premium(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/select-tier",
                data={"mode": "premium"},
                follow_redirects=False,
            )
            assert resp.status_code == 200
            assert resp.headers.get("hx-redirect") == "/step/2"


class TestStep2Profile:
    @pytest.mark.asyncio
    async def test_step2_renders_persona_cards(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # First select tier to create session
            await client.post("/api/select-tier", data={"mode": "basic"})
            resp = await client.get("/step/2")
            assert resp.status_code == 200
            # Should contain persona names from bank
            assert "Arjun Mehta" in resp.text or "Custom" in resp.text

    @pytest.mark.asyncio
    async def test_select_persona(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/api/select-tier", data={"mode": "basic"})
            resp = await client.post(
                "/api/select-persona",
                data={"persona_id": "P01"},
                follow_redirects=False,
            )
            assert resp.status_code == 200
            assert resp.headers.get("hx-redirect") == "/step/3"

    @pytest.mark.asyncio
    async def test_submit_custom_profile(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/api/select-tier", data={"mode": "basic"})
            resp = await client.post(
                "/api/submit-profile",
                data={
                    "name": "Test User",
                    "age": "30",
                    "monthly_sip": "50000",
                    "existing_corpus": "0",
                    "risk_appetite": "moderate",
                    "horizon_years": "10",
                    "goals": ["retirement", "wealth_building"],
                    "life_stage": "early career",
                    "preferences": "",
                },
                follow_redirects=False,
            )
            assert resp.status_code == 200
            assert resp.headers.get("hx-redirect") == "/step/3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py::TestStep1TierSelection -v`
Expected: FAIL — 404 on `/step/1`

- [ ] **Step 3: Create step_plan.html (Step 1)**

```html
<!-- apps/web/templates/step_plan.html -->
{% extends "base.html" %}

{% block title %}Choose Your Plan — FinAdvisor{% endblock %}

{% block content %}
<div class="text-center mb-8">
    <h2 class="text-2xl font-bold text-slate-900">Choose Your Plan</h2>
    <p class="text-slate-500 mt-2">Get a personalised mutual fund investment plan built by AI</p>
</div>

<div class="grid md:grid-cols-2 gap-6 max-w-3xl mx-auto">

    <!-- Basic Card -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-8 hover:shadow-md transition-shadow flex flex-col">
        <div class="flex-1">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-xl font-bold text-slate-900">Basic</h3>
                <span class="text-xs font-semibold px-2.5 py-1 rounded-full bg-primary-50 text-primary-600">Free</span>
            </div>
            <p class="text-slate-500 text-sm mb-6">Get a solid investment plan tailored to your goals</p>
            <ul class="space-y-3 text-sm text-slate-600 mb-8">
                <li class="flex items-start"><span class="text-primary-600 mr-2 mt-0.5">✓</span> Personalised fund selection</li>
                <li class="flex items-start"><span class="text-primary-600 mr-2 mt-0.5">✓</span> Corpus projections (bear / base / bull)</li>
                <li class="flex items-start"><span class="text-primary-600 mr-2 mt-0.5">✓</span> Risk analysis &amp; rebalancing guidance</li>
                <li class="flex items-start"><span class="text-primary-600 mr-2 mt-0.5">✓</span> Plain-language explanations</li>
            </ul>
        </div>
        <button
            hx-post="/api/select-tier"
            hx-vals='{"mode": "basic"}'
            class="w-full py-3 px-4 rounded-lg bg-primary-600 text-white font-semibold hover:bg-primary-700 transition-colors cursor-pointer"
        >Start Free Plan</button>
    </div>

    <!-- Premium Card -->
    <div class="bg-white rounded-lg shadow-sm border-2 border-amber-300 p-8 hover:shadow-md transition-shadow flex flex-col relative">
        <div class="flex-1">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-xl font-bold text-slate-900">Premium</h3>
                <span class="text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-50 text-amber-700">Premium</span>
            </div>
            <p class="text-slate-500 text-sm mb-6">Multiple expert perspectives compared by AI evaluator</p>
            <ul class="space-y-3 text-sm text-slate-600 mb-8">
                <li class="flex items-start"><span class="text-amber-500 mr-2 mt-0.5">✓</span> Everything in Basic</li>
                <li class="flex items-start"><span class="text-amber-500 mr-2 mt-0.5">✓</span> 3-5 strategic viewpoints generated</li>
                <li class="flex items-start"><span class="text-amber-500 mr-2 mt-0.5">✓</span> AI evaluator picks the best plan</li>
                <li class="flex items-start"><span class="text-amber-500 mr-2 mt-0.5">✓</span> SIP step-up schedules</li>
                <li class="flex items-start"><span class="text-amber-500 mr-2 mt-0.5">✓</span> Allocation phase timeline</li>
            </ul>
        </div>
        <button
            hx-post="/api/select-tier"
            hx-vals='{"mode": "premium"}'
            data-tier="premium"
            class="w-full py-3 px-4 rounded-lg bg-amber-500 text-white font-semibold hover:bg-amber-600 transition-colors cursor-pointer"
        >Start Premium Plan</button>
    </div>

</div>
{% endblock %}
```

- [ ] **Step 4: Create step_profile.html (Step 2)**

```html
<!-- apps/web/templates/step_profile.html -->
{% extends "base.html" %}

{% block title %}Your Profile — FinAdvisor{% endblock %}

{% block content %}
<div class="text-center mb-8">
    <h2 class="text-2xl font-bold text-slate-900">Tell Us About You</h2>
    <p class="text-slate-500 mt-2">Pick a sample profile to get started quickly, or fill in your own details</p>
</div>

<!-- Tab Toggle -->
<div class="flex justify-center mb-8">
    <div class="inline-flex rounded-lg border border-gray-200 bg-white p-1">
        <button id="tab-quick" onclick="switchTab('quick')" class="px-4 py-2 text-sm font-medium rounded-md bg-primary-600 text-white transition-colors">Quick Start</button>
        <button id="tab-custom" onclick="switchTab('custom')" class="px-4 py-2 text-sm font-medium rounded-md text-slate-600 hover:text-slate-900 transition-colors">Custom Profile</button>
    </div>
</div>

<!-- Quick Start: Persona Cards -->
<div id="panel-quick">
    <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {% for persona in personas %}
        <div
            class="bg-white rounded-lg shadow-sm border border-gray-200 p-5 hover:shadow-md hover:border-primary-300 transition-all cursor-pointer"
            hx-post="/api/select-persona"
            hx-vals='{"persona_id": "{{ persona.id }}"}'
        >
            <div class="flex items-center justify-between mb-3">
                <h3 class="font-semibold text-slate-900">{{ persona.name }}</h3>
                <span class="text-xs font-medium px-2 py-0.5 rounded-full
                    {% if persona.risk_appetite == 'aggressive' %}bg-red-50 text-red-700
                    {% elif persona.risk_appetite == 'moderate' %}bg-amber-50 text-amber-700
                    {% else %}bg-green-50 text-green-700{% endif %}
                ">{{ persona.risk_appetite | title }}</span>
            </div>
            <div class="text-sm text-slate-500 space-y-1">
                <p>Age {{ persona.age }} · {{ persona.investment_horizon_years }}yr horizon</p>
                <p class="font-medium text-slate-700">₹{{ "{:,.0f}".format(persona.monthly_investible_surplus_inr) }}/mo</p>
                <p class="text-xs text-slate-400 line-clamp-2">{{ persona.financial_goals | join(", ") }}</p>
            </div>
        </div>
        {% endfor %}
    </div>
</div>

<!-- Custom Profile Form -->
<div id="panel-custom" class="hidden">
    <form
        class="bg-white rounded-lg shadow-sm border border-gray-200 p-8 max-w-2xl mx-auto space-y-6"
        hx-post="/api/submit-profile"
        hx-indicator="#profile-spinner"
    >
        <div class="grid sm:grid-cols-2 gap-4">
            <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">Name</label>
                <input type="text" name="name" required class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500">
            </div>
            <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">Age</label>
                <input type="number" name="age" min="18" max="80" required class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500">
            </div>
        </div>

        <div class="grid sm:grid-cols-2 gap-4">
            <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">Monthly SIP Budget (₹)</label>
                <input type="number" name="monthly_sip" min="500" required class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500">
            </div>
            <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">Existing Corpus (₹)</label>
                <input type="number" name="existing_corpus" min="0" value="0" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500">
            </div>
        </div>

        <!-- Risk Appetite -->
        <div>
            <label class="block text-sm font-medium text-slate-700 mb-2">Risk Appetite</label>
            <div class="grid grid-cols-3 gap-3">
                {% for level, color, desc in [
                    ("conservative", "green", "Prefer safety"),
                    ("moderate", "amber", "Balanced approach"),
                    ("aggressive", "red", "Maximise growth")
                ] %}
                <label class="relative cursor-pointer">
                    <input type="radio" name="risk_appetite" value="{{ level }}" class="peer sr-only" {% if level == "moderate" %}checked{% endif %}>
                    <div class="rounded-lg border-2 border-gray-200 p-3 text-center peer-checked:border-primary-600 peer-checked:bg-primary-50 transition-colors">
                        <div class="text-sm font-semibold text-slate-900">{{ level | title }}</div>
                        <div class="text-xs text-slate-500 mt-1">{{ desc }}</div>
                    </div>
                </label>
                {% endfor %}
            </div>
        </div>

        <!-- Horizon Slider -->
        <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">
                Investment Horizon: <span id="horizon-label" class="font-bold text-primary-600">10</span> years
            </label>
            <input type="range" name="horizon_years" min="1" max="40" value="10"
                oninput="document.getElementById('horizon-label').textContent = this.value"
                class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600">
            <div class="flex justify-between text-xs text-slate-400 mt-1">
                <span>1 yr</span><span>10 yr</span><span>20 yr</span><span>40 yr</span>
            </div>
        </div>

        <!-- Goals -->
        <div>
            <label class="block text-sm font-medium text-slate-700 mb-2">Financial Goals</label>
            <div class="grid sm:grid-cols-2 gap-2">
                {% for goal_id, goal_label in [
                    ("retirement", "Retirement"),
                    ("children_education", "Children's Education"),
                    ("house_purchase", "House Purchase"),
                    ("wealth_building", "Wealth Building"),
                    ("emergency_fund", "Emergency Fund"),
                    ("other", "Other")
                ] %}
                <label class="flex items-center space-x-2 cursor-pointer">
                    <input type="checkbox" name="goals" value="{{ goal_id }}" class="rounded border-gray-300 text-primary-600 focus:ring-primary-500">
                    <span class="text-sm text-slate-600">{{ goal_label }}</span>
                </label>
                {% endfor %}
            </div>
        </div>

        <!-- Life Stage -->
        <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">Life Stage</label>
            <select name="life_stage" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500">
                <option value="student">Student</option>
                <option value="early career" selected>Early Career</option>
                <option value="mid career">Mid Career</option>
                <option value="pre-retirement">Pre-Retirement</option>
                <option value="retired">Retired</option>
            </select>
        </div>

        <!-- Preferences -->
        <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">Additional Preferences (optional)</label>
            <textarea name="preferences" rows="2" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500" placeholder="e.g. prefer index funds, interested in tech sector..."></textarea>
        </div>

        <button type="submit" class="w-full py-3 px-4 rounded-lg bg-primary-600 text-white font-semibold hover:bg-primary-700 transition-colors cursor-pointer flex items-center justify-center">
            <span>Continue</span>
            <span id="profile-spinner" class="htmx-indicator ml-2">
                <svg class="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
            </span>
        </button>
    </form>
</div>

{% endblock %}

{% block scripts %}
<script>
function switchTab(tab) {
    const quickPanel = document.getElementById('panel-quick');
    const customPanel = document.getElementById('panel-custom');
    const quickTab = document.getElementById('tab-quick');
    const customTab = document.getElementById('tab-custom');

    if (tab === 'quick') {
        quickPanel.classList.remove('hidden');
        customPanel.classList.add('hidden');
        quickTab.classList.add('bg-primary-600', 'text-white');
        quickTab.classList.remove('text-slate-600');
        customTab.classList.remove('bg-primary-600', 'text-white');
        customTab.classList.add('text-slate-600');
    } else {
        customPanel.classList.remove('hidden');
        quickPanel.classList.add('hidden');
        customTab.classList.add('bg-primary-600', 'text-white');
        customTab.classList.remove('text-slate-600');
        quickTab.classList.remove('bg-primary-600', 'text-white');
        quickTab.classList.add('text-slate-600');
    }
}
</script>
{% endblock %}
```

- [ ] **Step 5: Implement routes.py with Step 1 and Step 2 page routes**

```python
# apps/web/routes.py
"""Page routes for the FinAdvisor wizard steps."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from apps.web.session import Session

router = APIRouter()


async def _get_or_create_session(request: Request, session_id: str | None = None) -> tuple[Session, str]:
    """Get existing session or create new one. Returns (session, session_id)."""
    store = request.app.state.session_store
    if session_id:
        session = await store.get(session_id)
        if session:
            return session, session_id
    session = Session()
    await store.save(session)
    return session, session.id


@router.get("/step/1", response_class=HTMLResponse)
async def step_plan(request: Request, finadvisor_session: str | None = Cookie(default=None)):
    session, sid = await _get_or_create_session(request, finadvisor_session)
    templates = request.app.state.templates
    response = templates.TemplateResponse(
        "step_plan.html",
        {"request": request, "current_step": 1, "session": session},
    )
    response.set_cookie("finadvisor_session", sid, httponly=True, samesite="lax")
    return response


@router.get("/step/2", response_class=HTMLResponse)
async def step_profile(request: Request, finadvisor_session: str | None = Cookie(default=None)):
    store = request.app.state.session_store
    session = await store.get(finadvisor_session) if finadvisor_session else None
    if not session:
        return RedirectResponse(url="/step/1", status_code=307)

    from subprime.evaluation.personas import load_personas

    personas = load_personas()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "step_profile.html",
        {"request": request, "current_step": 2, "session": session, "personas": personas},
    )


@router.get("/step/3", response_class=HTMLResponse)
async def step_strategy(request: Request, finadvisor_session: str | None = Cookie(default=None)):
    store = request.app.state.session_store
    session = await store.get(finadvisor_session) if finadvisor_session else None
    if not session or not session.profile:
        return RedirectResponse(url="/step/1", status_code=307)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "step_strategy.html",
        {"request": request, "current_step": 3, "session": session},
    )


@router.get("/step/4", response_class=HTMLResponse)
async def step_result(request: Request, finadvisor_session: str | None = Cookie(default=None)):
    store = request.app.state.session_store
    session = await store.get(finadvisor_session) if finadvisor_session else None
    if not session or not session.plan:
        return RedirectResponse(url="/step/1", status_code=307)

    from apps.web.rendering import (
        chart_data_corpus,
        chart_data_donut,
        format_inr,
        render_markdown,
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "step_result.html",
        {
            "request": request,
            "current_step": 4,
            "session": session,
            "plan": session.plan,
            "profile": session.profile,
            "strategy": session.strategy,
            "format_inr": format_inr,
            "render_markdown": render_markdown,
            "chart_data_donut": chart_data_donut,
            "chart_data_corpus": chart_data_corpus,
        },
    )
```

- [ ] **Step 6: Implement api.py with select-tier, select-persona, submit-profile endpoints**

```python
# apps/web/api.py
"""HTMX API endpoints for the FinAdvisor wizard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request, Response

from apps.web.session import Session
from subprime.core.models import InvestorProfile

router = APIRouter(prefix="/api")

_GOAL_LABELS = {
    "retirement": "Retirement",
    "children_education": "Children's Education",
    "house_purchase": "House Purchase",
    "wealth_building": "Wealth Building",
    "emergency_fund": "Emergency Fund",
    "other": "Other",
}


async def _get_session(request: Request, session_id: str | None) -> Session | None:
    if not session_id:
        return None
    return await request.app.state.session_store.get(session_id)


@router.post("/select-tier")
async def select_tier(
    request: Request,
    mode: Annotated[str, Form()],
    finadvisor_session: str | None = Cookie(default=None),
):
    store = request.app.state.session_store
    session = await _get_session(request, finadvisor_session)
    if not session:
        session = Session()

    session.mode = mode  # type: ignore[assignment]
    session.current_step = 2
    await store.save(session)

    response = Response(status_code=200)
    response.headers["HX-Redirect"] = "/step/2"
    response.set_cookie("finadvisor_session", session.id, httponly=True, samesite="lax")
    return response


@router.post("/select-persona")
async def select_persona(
    request: Request,
    persona_id: Annotated[str, Form()],
    finadvisor_session: str | None = Cookie(default=None),
):
    store = request.app.state.session_store
    session = await _get_session(request, finadvisor_session)
    if not session:
        return Response("No session", status_code=400)

    from subprime.evaluation.personas import get_persona

    profile = get_persona(persona_id)
    session.profile = profile
    session.current_step = 3
    await store.save(session)

    response = Response(status_code=200)
    response.headers["HX-Redirect"] = "/step/3"
    return response


@router.post("/submit-profile")
async def submit_profile(
    request: Request,
    name: Annotated[str, Form()],
    age: Annotated[int, Form()],
    monthly_sip: Annotated[float, Form()],
    existing_corpus: Annotated[float, Form()] = 0,
    risk_appetite: Annotated[str, Form()] = "moderate",
    horizon_years: Annotated[int, Form()] = 10,
    goals: Annotated[list[str], Form()] = [],
    life_stage: Annotated[str, Form()] = "early career",
    preferences: Annotated[str, Form()] = "",
    finadvisor_session: str | None = Cookie(default=None),
):
    store = request.app.state.session_store
    session = await _get_session(request, finadvisor_session)
    if not session:
        return Response("No session", status_code=400)

    goal_labels = [_GOAL_LABELS.get(g, g) for g in goals]

    profile = InvestorProfile(
        id="custom",
        name=name,
        age=age,
        risk_appetite=risk_appetite,  # type: ignore[arg-type]
        investment_horizon_years=horizon_years,
        monthly_investible_surplus_inr=monthly_sip,
        existing_corpus_inr=existing_corpus,
        liabilities_inr=0,
        financial_goals=goal_labels if goal_labels else ["Wealth Building"],
        life_stage=life_stage,
        tax_bracket="new_regime",
        preferences=preferences or None,
    )

    session.profile = profile
    session.current_step = 3
    await store.save(session)

    response = Response(status_code=200)
    response.headers["HX-Redirect"] = "/step/3"
    return response
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py::TestStep1TierSelection tests/test_web_wizard.py::TestStep2Profile -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add apps/web/routes.py apps/web/api.py apps/web/templates/step_plan.html apps/web/templates/step_profile.html tests/test_web_wizard.py
git commit -m "feat(web): step 1 tier selection and step 2 profile form with persona cards"
```

---

### Task 5: Step 3 (Strategy Dashboard + Chat)

**Files:**
- Create: `apps/web/templates/step_strategy.html`
- Create: `apps/web/templates/partials/strategy_dashboard.html`
- Create: `apps/web/templates/partials/strategy_chat.html`
- Create: `apps/web/templates/partials/loading.html`
- Modify: `apps/web/api.py`
- Modify: `tests/test_web_wizard.py`

- [ ] **Step 1: Write the failing tests for strategy generation and revision endpoints**

Append to `tests/test_web_wizard.py`:

```python
from unittest.mock import AsyncMock, patch

from subprime.core.models import StrategyOutline


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


class TestStep3Strategy:
    @pytest.mark.asyncio
    async def test_step3_redirects_without_profile(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/step/3", follow_redirects=False)
            assert resp.status_code == 307

    @pytest.mark.asyncio
    async def test_generate_strategy_endpoint(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Setup: create session with profile
            await client.post("/api/select-tier", data={"mode": "basic"})
            await client.post("/api/select-persona", data={"persona_id": "P01"})

            with patch(
                "apps.web.api.generate_strategy",
                new_callable=AsyncMock,
                return_value=_mock_strategy(),
            ):
                resp = await client.get("/api/generate-strategy")
                assert resp.status_code == 200
                assert "Equity" in resp.text

    @pytest.mark.asyncio
    async def test_revise_strategy_endpoint(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/api/select-tier", data={"mode": "basic"})
            await client.post("/api/select-persona", data={"persona_id": "P01"})

            mock_strategy = _mock_strategy()
            store = app.state.session_store
            # Manually set strategy on session
            sessions = list(store._sessions.values())
            sessions[0].strategy = mock_strategy
            await store.save(sessions[0])

            revised = _mock_strategy()
            revised.equity_pct = 60
            revised.debt_pct = 30

            with patch(
                "apps.web.api.generate_strategy",
                new_callable=AsyncMock,
                return_value=revised,
            ):
                resp = await client.post(
                    "/api/revise-strategy",
                    data={"feedback": "More conservative please"},
                )
                assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py::TestStep3Strategy -v`
Expected: FAIL

- [ ] **Step 3: Create step_strategy.html**

```html
<!-- apps/web/templates/step_strategy.html -->
{% extends "base.html" %}

{% block title %}Strategy — FinAdvisor{% endblock %}

{% block content %}
<div class="text-center mb-8">
    <h2 class="text-2xl font-bold text-slate-900">Your Investment Strategy</h2>
    <p class="text-slate-500 mt-2">
        {{ session.profile.name }}, {{ session.profile.age }} · {{ session.mode | title }} plan · {{ session.profile.investment_horizon_years }}yr horizon
    </p>
</div>

<!-- Strategy Dashboard (loaded via HTMX) -->
<div id="strategy-content"
     hx-get="/api/generate-strategy"
     hx-trigger="load"
     hx-indicator="#strategy-loading"
>
    <!-- Loading skeleton -->
    <div id="strategy-loading" class="htmx-indicator">
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
            <div class="text-center">
                <svg class="animate-spin h-8 w-8 text-primary-600 mx-auto mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
                <p class="text-slate-500">Crafting your strategy...</p>
            </div>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="/static/charts.js"></script>
{% endblock %}
```

- [ ] **Step 4: Create partials/strategy_dashboard.html**

```html
<!-- apps/web/templates/partials/strategy_dashboard.html -->
<div class="fade-in space-y-6">

    <!-- Asset Allocation + Info -->
    <div class="grid md:grid-cols-2 gap-6">
        <!-- Donut Chart -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h3 class="text-sm font-semibold text-slate-900 mb-4">Asset Allocation</h3>
            <div class="flex justify-center">
                <canvas id="allocation-chart" width="220" height="220"
                    data-labels='{{ chart_data.labels | tojson }}'
                    data-values='{{ chart_data.values | tojson }}'
                    data-colors='{{ chart_data.colors | tojson }}'
                ></canvas>
            </div>
        </div>

        <!-- Strategy Details -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 space-y-4">
            <div>
                <h3 class="text-sm font-semibold text-slate-900 mb-2">Approach</h3>
                <p class="text-sm text-slate-600">{{ strategy.equity_approach }}</p>
            </div>
            <div>
                <h3 class="text-sm font-semibold text-slate-900 mb-2">Key Themes</h3>
                <div class="flex flex-wrap gap-2">
                    {% for theme in strategy.key_themes %}
                    <span class="text-xs font-medium px-2.5 py-1 rounded-full bg-primary-50 text-primary-700">{{ theme }}</span>
                    {% endfor %}
                </div>
            </div>
            <div>
                <h3 class="text-sm font-semibold text-slate-900 mb-2">Expected Returns</h3>
                <p class="text-sm text-slate-600">{{ strategy.risk_return_summary }}</p>
            </div>
        </div>
    </div>

    {% if strategy.open_questions %}
    <div class="bg-amber-50 border border-amber-200 rounded-lg p-4">
        <h3 class="text-sm font-semibold text-amber-800 mb-2">Points to Consider</h3>
        <ul class="text-sm text-amber-700 space-y-1 list-disc list-inside">
            {% for q in strategy.open_questions %}
            <li>{{ q }}</li>
            {% endfor %}
        </ul>
    </div>
    {% endif %}

    <!-- Chat Feedback Section -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div id="strategy-chat" class="space-y-3 mb-4">
            <!-- Chat messages will be appended here -->
        </div>

        <div class="flex gap-3">
            <input
                type="text"
                id="strategy-feedback"
                name="feedback"
                placeholder="Want to adjust anything? Tell me what to change..."
                class="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                hx-post="/api/revise-strategy"
                hx-trigger="keyup[key=='Enter']"
                hx-target="#strategy-content"
                hx-include="this"
                hx-indicator="#revise-spinner"
            >
            <button
                hx-post="/api/generate-plan"
                hx-indicator="#plan-spinner"
                class="px-6 py-2 rounded-lg bg-primary-600 text-white font-semibold hover:bg-primary-700 transition-colors text-sm whitespace-nowrap flex items-center gap-2"
            >
                Generate My Plan
                <span id="plan-spinner" class="htmx-indicator">
                    <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
                </span>
            </button>
        </div>
        <span id="revise-spinner" class="htmx-indicator text-xs text-slate-400 mt-1 inline-block">Revising strategy...</span>
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', function() {
    initDonutChart('allocation-chart');
});
// Also handle HTMX swaps
document.body.addEventListener('htmx:afterSwap', function() {
    const canvas = document.getElementById('allocation-chart');
    if (canvas) initDonutChart('allocation-chart');
});
</script>
```

- [ ] **Step 5: Create partials/loading.html**

```html
<!-- apps/web/templates/partials/loading.html -->
<div class="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
    <div class="text-center">
        <svg class="animate-spin h-8 w-8 text-primary-600 mx-auto mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
        <p class="text-slate-500">{{ message | default("Loading...") }}</p>
    </div>
</div>
```

- [ ] **Step 6: Add generate-strategy, revise-strategy, generate-plan endpoints to api.py**

Append to `apps/web/api.py`:

```python
from subprime.advisor.planner import generate_plan, generate_strategy
from subprime.core.models import ConversationTurn

from apps.web.rendering import chart_data_donut, render_markdown


@router.get("/generate-strategy")
async def api_generate_strategy(
    request: Request,
    finadvisor_session: str | None = Cookie(default=None),
):
    store = request.app.state.session_store
    session = await _get_session(request, finadvisor_session)
    if not session or not session.profile:
        return Response("No profile", status_code=400)

    strategy = await generate_strategy(session.profile)
    session.strategy = strategy
    session.current_step = 3
    await store.save(session)

    chart_data = chart_data_donut(
        strategy.equity_pct, strategy.debt_pct, strategy.gold_pct, strategy.other_pct,
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/strategy_dashboard.html",
        {"request": request, "strategy": strategy, "chart_data": chart_data},
    )


@router.post("/revise-strategy")
async def api_revise_strategy(
    request: Request,
    feedback: Annotated[str, Form()],
    finadvisor_session: str | None = Cookie(default=None),
):
    store = request.app.state.session_store
    session = await _get_session(request, finadvisor_session)
    if not session or not session.strategy:
        return Response("No strategy", status_code=400)

    session.strategy_chat.append(ConversationTurn(role="user", content=feedback))

    strategy = await generate_strategy(
        session.profile,
        feedback=feedback,
        current_strategy=session.strategy,
    )
    session.strategy = strategy
    await store.save(session)

    chart_data = chart_data_donut(
        strategy.equity_pct, strategy.debt_pct, strategy.gold_pct, strategy.other_pct,
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/strategy_dashboard.html",
        {"request": request, "strategy": strategy, "chart_data": chart_data},
    )


@router.post("/generate-plan")
async def api_generate_plan(
    request: Request,
    finadvisor_session: str | None = Cookie(default=None),
):
    store = request.app.state.session_store
    session = await _get_session(request, finadvisor_session)
    if not session or not session.profile:
        return Response("No profile", status_code=400)

    n_perspectives = 3
    plan = await generate_plan(
        session.profile,
        strategy=session.strategy,
        mode=session.mode,
        n_perspectives=n_perspectives,
    )
    session.plan = plan
    session.current_step = 4
    await store.save(session)

    response = Response(status_code=200)
    response.headers["HX-Redirect"] = "/step/4"
    return response


@router.post("/reset")
async def api_reset(
    request: Request,
    finadvisor_session: str | None = Cookie(default=None),
):
    store = request.app.state.session_store
    # Create a fresh session
    new_session = Session()
    await store.save(new_session)

    response = Response(status_code=200)
    response.headers["HX-Redirect"] = "/step/1"
    response.set_cookie("finadvisor_session", new_session.id, httponly=True, samesite="lax")
    return response
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py::TestStep3Strategy -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add apps/web/templates/step_strategy.html apps/web/templates/partials/strategy_dashboard.html apps/web/templates/partials/strategy_chat.html apps/web/templates/partials/loading.html apps/web/api.py tests/test_web_wizard.py
git commit -m "feat(web): step 3 strategy dashboard with donut chart and revision chat"
```

---

### Task 6: Step 4 (Plan Results Page) + Charts

**Files:**
- Create: `apps/web/templates/step_result.html`
- Create: `apps/web/static/charts.js`
- Modify: `tests/test_web_wizard.py`

- [ ] **Step 1: Write the failing tests for step 4 rendering**

Append to `tests/test_web_wizard.py`:

```python
from subprime.core.models import Allocation, InvestmentPlan, MutualFund


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
        rationale="This plan balances growth and stability for a moderate risk investor with a 10-year horizon.",
        risks=["Market volatility can cause 20-30% temporary drops", "Debt funds can lose value if interest rates rise sharply"],
        setup_phase="1. Open an account on Kuvera or Groww\n2. Start SIPs in all three funds\n3. Set up auto-debit from your bank",
        rebalancing_guidelines="Check once a year. If equity has grown to more than 75% of your portfolio, move some to debt.",
        disclaimer="For research/educational purposes only. Not certified financial advice.",
    )


class TestStep4PlanResult:
    @pytest.mark.asyncio
    async def test_step4_redirects_without_plan(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/step/4", follow_redirects=False)
            assert resp.status_code == 307

    @pytest.mark.asyncio
    async def test_step4_renders_plan(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Build up session state
            await client.post("/api/select-tier", data={"mode": "basic"})
            await client.post("/api/select-persona", data={"persona_id": "P01"})

            # Manually inject plan into session
            store = app.state.session_store
            sessions = list(store._sessions.values())
            session = sessions[0]
            session.plan = _mock_plan()
            session.current_step = 4
            await store.save(session)

            resp = await client.get("/step/4")
            assert resp.status_code == 200
            assert "UTI Nifty 50" in resp.text
            assert "Parag Parikh" in resp.text
            assert "HDFC Short Term" in resp.text

    @pytest.mark.asyncio
    async def test_reset_endpoint(self):
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/api/select-tier", data={"mode": "basic"})
            resp = await client.post("/api/reset")
            assert resp.status_code == 200
            assert resp.headers.get("hx-redirect") == "/step/1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py::TestStep4PlanResult -v`
Expected: FAIL — template `step_result.html` not found

- [ ] **Step 3: Create charts.js**

```javascript
// apps/web/static/charts.js

/**
 * Initialize a donut chart from data-* attributes on a canvas element.
 * Expects: data-labels='["Equity","Debt"]' data-values='[70,30]' data-colors='["#4f46e5","#0891b2"]'
 */
function initDonutChart(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const labels = JSON.parse(canvas.dataset.labels || '[]');
    const values = JSON.parse(canvas.dataset.values || '[]');
    const colors = JSON.parse(canvas.dataset.colors || '[]');

    // Destroy existing chart if any
    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: '#ffffff',
            }]
        },
        options: {
            responsive: false,
            cutout: '60%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { padding: 16, usePointStyle: true, pointStyle: 'circle' }
                },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return ctx.label + ': ' + ctx.parsed + '%';
                        }
                    }
                }
            }
        }
    });
}

/**
 * Initialize a corpus projection bar chart.
 * Expects: data-scenarios as JSON array of {label, future_value, present_value, color, future_value_fmt, present_value_fmt}
 */
function initCorpusChart(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const scenarios = JSON.parse(canvas.dataset.scenarios || '[]');
    if (scenarios.length === 0) return;

    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    const labels = scenarios.map(s => s.label);
    const futureValues = scenarios.map(s => s.future_value);
    const presentValues = scenarios.map(s => s.present_value);
    const colors = scenarios.map(s => s.color);

    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Future Value',
                    data: futureValues,
                    backgroundColor: colors.map(c => c + 'cc'),
                    borderColor: colors,
                    borderWidth: 1,
                },
                {
                    label: "Today's ₹",
                    data: presentValues,
                    backgroundColor: colors.map(c => c + '66'),
                    borderColor: colors,
                    borderWidth: 1,
                    borderDash: [5, 5],
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            const idx = ctx.dataIndex;
                            const s = scenarios[idx];
                            if (ctx.datasetIndex === 0) return 'Future: ' + s.future_value_fmt;
                            return "Today's ₹: " + s.present_value_fmt;
                        }
                    }
                },
                legend: { position: 'bottom', labels: { usePointStyle: true } }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            if (value >= 10000000) return '₹' + (value / 10000000).toFixed(1) + ' Cr';
                            if (value >= 100000) return '₹' + (value / 100000).toFixed(1) + ' L';
                            return '₹' + value.toLocaleString('en-IN');
                        }
                    }
                }
            }
        }
    });
}
```

- [ ] **Step 4: Create step_result.html**

```html
<!-- apps/web/templates/step_result.html -->
{% extends "base.html" %}

{% block title %}Your Plan — FinAdvisor{% endblock %}

{% block content %}
<div class="fade-in space-y-6">

    <div class="text-center mb-4">
        <h2 class="text-2xl font-bold text-slate-900">Your Investment Plan</h2>
        <p class="text-slate-500 mt-1">
            {{ profile.name }}, {{ profile.age }} · {{ session.mode | title }} · {{ profile.investment_horizon_years }}yr horizon
        </p>
    </div>

    <!-- Stat Cards -->
    {% set n_funds = plan.allocations | length %}
    {% set houses = plan.allocations | map(attribute='fund.fund_house') | select | unique | list %}
    {% set total_sip = plan.allocations | map(attribute='monthly_sip_inr') | select | sum %}
    {% set bear = plan.projected_returns.get('bear', 0) %}
    {% set base_r = plan.projected_returns.get('base', 0) %}
    {% set bull = plan.projected_returns.get('bull', 0) %}

    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 text-center">
            <div class="text-xs text-slate-400 uppercase tracking-wide">Funds</div>
            <div class="text-lg font-bold text-slate-900 mt-1">{{ n_funds }}</div>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 text-center">
            <div class="text-xs text-slate-400 uppercase tracking-wide">Fund Houses</div>
            <div class="text-lg font-bold text-slate-900 mt-1">{{ houses | length }}</div>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 text-center">
            <div class="text-xs text-slate-400 uppercase tracking-wide">Monthly SIP</div>
            <div class="text-lg font-bold text-green-600 mt-1">{{ format_inr(total_sip) }}</div>
        </div>
        {% if bear > 0 %}
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 text-center">
            <div class="text-xs text-slate-400 uppercase tracking-wide">Bear</div>
            <div class="text-lg font-bold text-red-500 mt-1">{{ "%.1f" | format(bear) }}%</div>
        </div>
        {% endif %}
        {% if base_r > 0 %}
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 text-center">
            <div class="text-xs text-slate-400 uppercase tracking-wide">Base</div>
            <div class="text-lg font-bold text-amber-500 mt-1">{{ "%.1f" | format(base_r) }}%</div>
        </div>
        {% endif %}
        {% if bull > 0 %}
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 text-center">
            <div class="text-xs text-slate-400 uppercase tracking-wide">Bull</div>
            <div class="text-lg font-bold text-green-500 mt-1">{{ "%.1f" | format(bull) }}%</div>
        </div>
        {% endif %}
    </div>

    <!-- Corpus Projection Chart -->
    {% set effective_sip = profile.monthly_investible_surplus_inr if profile else total_sip %}
    {% set effective_horizon = profile.investment_horizon_years if profile else 0 %}
    {% if bear > 0 and effective_sip > 0 and effective_horizon > 0 %}
    {% set corpus_data = chart_data_corpus(effective_sip, effective_horizon, bear, base_r, bull) %}
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 class="text-sm font-semibold text-slate-900 mb-1">
            Projected Corpus
            <span class="font-normal text-slate-500">(SIP {{ format_inr(effective_sip) }}/mo over {{ effective_horizon }} years)</span>
        </h3>
        <div class="h-64">
            <canvas id="corpus-chart"
                data-scenarios='{{ corpus_data.scenarios | tojson }}'
            ></canvas>
        </div>
        <!-- Corpus table -->
        <table class="w-full text-sm mt-4">
            <thead>
                <tr class="border-b border-gray-200">
                    <th class="text-left py-2 text-slate-500 font-medium">Scenario</th>
                    <th class="text-right py-2 text-slate-500 font-medium">CAGR</th>
                    <th class="text-right py-2 text-slate-500 font-medium">Future Value</th>
                    <th class="text-right py-2 text-slate-500 font-medium">In Today's ₹</th>
                </tr>
            </thead>
            <tbody>
                {% for s in corpus_data.scenarios %}
                <tr class="border-b border-gray-100">
                    <td class="py-2 font-semibold" style="color: {{ s.color }}">{{ s.label }}</td>
                    <td class="text-right py-2" style="color: {{ s.color }}">{{ s.cagr }}%</td>
                    <td class="text-right py-2" style="color: {{ s.color }}">{{ s.future_value_fmt }}</td>
                    <td class="text-right py-2" style="color: {{ s.color }}">{{ s.present_value_fmt }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}

    <!-- Fund Allocations Table -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-200">
            <h3 class="text-sm font-semibold text-slate-900">Fund Allocations</h3>
        </div>
        <div class="divide-y divide-gray-100">
            {% for alloc in plan.allocations %}
            <details class="group">
                <summary class="flex items-center px-6 py-4 cursor-pointer hover:bg-gray-50 transition-colors">
                    <div class="flex-1 min-w-0">
                        <div class="font-semibold text-slate-900 text-sm">{{ alloc.fund.name }}</div>
                        <div class="text-xs text-slate-400 mt-0.5">{{ alloc.fund.fund_house }} · {{ alloc.fund.amfi_code }}</div>
                    </div>
                    <div class="flex items-center gap-4 text-sm shrink-0 ml-4">
                        <span class="font-bold text-slate-900 w-12 text-right">{{ "%.0f" | format(alloc.allocation_pct) }}%</span>
                        <span class="text-slate-500 w-12 text-center">{{ alloc.mode }}</span>
                        <span class="text-green-600 font-medium w-20 text-right">{% if alloc.monthly_sip_inr %}{{ format_inr(alloc.monthly_sip_inr) }}{% else %}-{% endif %}</span>
                        <span class="text-slate-400 w-14 text-right">{% if alloc.fund.expense_ratio %}{{ "%.2f" | format(alloc.fund.expense_ratio) }}%{% else %}-{% endif %}</span>
                        <span class="stars w-16 text-center">{% if alloc.fund.morningstar_rating %}{{ "★" * alloc.fund.morningstar_rating }}{% else %}-{% endif %}</span>
                        <svg class="w-4 h-4 text-slate-400 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
                    </div>
                </summary>
                <div class="px-6 pb-4 pt-0">
                    <div class="prose-commentary text-sm text-slate-600 bg-gray-50 rounded-md p-4">
                        {{ render_markdown(alloc.rationale) | safe }}
                    </div>
                </div>
            </details>
            {% endfor %}
        </div>
    </div>

    <!-- Why This Plan -->
    {% if plan.rationale %}
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 class="text-sm font-semibold text-slate-900 mb-3">Why This Plan</h3>
        <div class="prose-commentary text-sm text-slate-600 leading-relaxed">
            {{ render_markdown(plan.rationale) | safe }}
        </div>
    </div>
    {% endif %}

    <!-- Collapsible Sections -->
    {% if plan.risks %}
    <details class="bg-white rounded-lg shadow-sm border border-gray-200">
        <summary class="px-6 py-4 cursor-pointer hover:bg-gray-50 font-semibold text-sm text-slate-900">Risks to Know About</summary>
        <div class="px-6 pb-4">
            <ul class="text-sm text-slate-600 space-y-2">
                {% for risk in plan.risks %}
                <li class="flex items-start"><span class="text-red-400 mr-2 mt-0.5">•</span>{{ risk }}</li>
                {% endfor %}
            </ul>
        </div>
    </details>
    {% endif %}

    {% if plan.setup_phase %}
    <details class="bg-white rounded-lg shadow-sm border border-gray-200">
        <summary class="px-6 py-4 cursor-pointer hover:bg-gray-50 font-semibold text-sm text-slate-900">Getting Started</summary>
        <div class="px-6 pb-4 prose-commentary text-sm text-slate-600">
            {{ render_markdown(plan.setup_phase) | safe }}
        </div>
    </details>
    {% endif %}

    {% if plan.rebalancing_guidelines %}
    <details class="bg-white rounded-lg shadow-sm border border-gray-200">
        <summary class="px-6 py-4 cursor-pointer hover:bg-gray-50 font-semibold text-sm text-slate-900">Rebalancing Guidelines</summary>
        <div class="px-6 pb-4 prose-commentary text-sm text-slate-600">
            {{ render_markdown(plan.rebalancing_guidelines) | safe }}
        </div>
    </details>
    {% endif %}

    <!-- Premium-only sections -->
    {% if plan.sip_step_up and session.mode == 'premium' %}
    <div class="bg-white rounded-lg shadow-sm border-2 border-amber-200 p-6">
        <h3 class="text-sm font-semibold text-slate-900 mb-2">
            SIP Step-Up Schedule
            <span class="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 ml-2">Premium</span>
        </h3>
        <p class="text-sm text-slate-600 mb-3">{{ plan.sip_step_up.description }}</p>
        <p class="text-sm text-slate-500">Annual increase: <span class="font-semibold">{{ "%.0f" | format(plan.sip_step_up.annual_increase_pct) }}%</span></p>
    </div>
    {% endif %}

    {% if plan.allocation_schedule and session.mode == 'premium' %}
    <div class="bg-white rounded-lg shadow-sm border-2 border-amber-200 p-6">
        <h3 class="text-sm font-semibold text-slate-900 mb-3">
            Allocation Phase Timeline
            <span class="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 ml-2">Premium</span>
        </h3>
        <table class="w-full text-sm">
            <thead>
                <tr class="border-b border-gray-200">
                    <th class="text-left py-2 text-slate-500 font-medium">Year</th>
                    <th class="text-right py-2 text-slate-500 font-medium">Equity</th>
                    <th class="text-right py-2 text-slate-500 font-medium">Debt</th>
                    <th class="text-right py-2 text-slate-500 font-medium">Gold</th>
                    <th class="text-left py-2 text-slate-500 font-medium pl-4">Trigger</th>
                </tr>
            </thead>
            <tbody>
                {% for phase in plan.allocation_schedule %}
                <tr class="border-b border-gray-100">
                    <td class="py-2 font-medium">Year {{ phase.year }}</td>
                    <td class="text-right py-2">{{ "%.0f" | format(phase.equity_pct) }}%</td>
                    <td class="text-right py-2">{{ "%.0f" | format(phase.debt_pct) }}%</td>
                    <td class="text-right py-2">{{ "%.0f" | format(phase.gold_pct) }}%</td>
                    <td class="text-left py-2 pl-4 text-slate-500">{{ phase.trigger }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}

    <!-- Disclaimer -->
    <p class="text-xs text-slate-400 italic text-center">{{ plan.disclaimer }}</p>

    <!-- Actions -->
    <div class="flex justify-center gap-4 pt-4">
        <button
            hx-post="/api/reset"
            class="px-6 py-2 rounded-lg border border-gray-300 text-slate-600 font-medium hover:bg-gray-50 transition-colors text-sm"
        >Start Over</button>
        <button
            disabled
            class="px-6 py-2 rounded-lg bg-gray-200 text-gray-400 font-medium text-sm cursor-not-allowed"
            title="Coming soon"
        >Download PDF</button>
    </div>

</div>
{% endblock %}

{% block scripts %}
<script src="/static/charts.js"></script>
<script>
document.addEventListener('DOMContentLoaded', function() {
    initCorpusChart('corpus-chart');
});
</script>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py::TestStep4PlanResult -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add apps/web/templates/step_result.html apps/web/static/charts.js tests/test_web_wizard.py
git commit -m "feat(web): step 4 plan results page with corpus chart, expandable allocations, markdown commentary"
```

---

### Task 7: Wiring — Dependencies, Dockerfile, CLI, Rename Old App

**Files:**
- Rename: `apps/web/app.py` → `apps/web/gradio_app.py`
- Modify: `pyproject.toml`
- Modify: `Dockerfile`
- Modify: `src/subprime/cli.py:355-381`
- Modify: `tests/test_web_wizard.py`

- [ ] **Step 1: Write the failing test for CLI web command launching uvicorn**

Append to `tests/test_web_wizard.py`:

```python
class TestCLIWebCommand:
    def test_web_command_imports_fastapi_app(self):
        """Verify the web command can import the new FastAPI app."""
        from apps.web.main import create_app

        app = create_app()
        assert app.title == "FinAdvisor"

    @pytest.mark.asyncio
    async def test_full_wizard_flow(self):
        """End-to-end flow: tier → persona → strategy → plan → result page."""
        from apps.web.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Step 1: Select basic tier
            resp = await client.post("/api/select-tier", data={"mode": "basic"})
            assert resp.headers.get("hx-redirect") == "/step/2"

            # Step 2: Select persona
            resp = await client.post("/api/select-persona", data={"persona_id": "P01"})
            assert resp.headers.get("hx-redirect") == "/step/3"

            # Step 3: Generate strategy (mocked)
            with patch(
                "apps.web.api.generate_strategy",
                new_callable=AsyncMock,
                return_value=_mock_strategy(),
            ):
                resp = await client.get("/api/generate-strategy")
                assert resp.status_code == 200

            # Inject strategy into session for plan generation
            store = app.state.session_store
            sessions = list(store._sessions.values())
            session = sessions[0]
            session.strategy = _mock_strategy()
            await store.save(session)

            # Step 3→4: Generate plan (mocked)
            with patch(
                "apps.web.api.generate_plan",
                new_callable=AsyncMock,
                return_value=_mock_plan(),
            ):
                resp = await client.post("/api/generate-plan")
                assert resp.headers.get("hx-redirect") == "/step/4"

            # Step 4: View plan
            resp = await client.get("/step/4")
            assert resp.status_code == 200
            assert "UTI Nifty 50" in resp.text

            # Reset
            resp = await client.post("/api/reset")
            assert resp.headers.get("hx-redirect") == "/step/1"
```

- [ ] **Step 2: Run test to verify it passes (should already pass at this point)**

Run: `cd /home/agent/projects/subprime && python -m pytest tests/test_web_wizard.py::TestCLIWebCommand -v`
Expected: PASS

- [ ] **Step 3: Rename old Gradio app**

```bash
mv apps/web/app.py apps/web/gradio_app.py
```

- [ ] **Step 4: Update pyproject.toml dependencies**

Replace `gradio>=5.0` with FastAPI dependencies in `pyproject.toml`:

```toml
dependencies = [
    "pydantic>=2.0",
    "pydantic-ai>=0.1.0",
    "pydantic-settings>=2.0",
    "anthropic>=0.40",
    "httpx>=0.27",
    "duckdb>=1.2",
    "rich>=13.0",
    "typer>=0.12",
    "scipy>=1.14",
    "numpy>=2.0",
    "python-dotenv>=1.0",
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "jinja2>=3.1",
    "python-multipart>=0.0.12",
    "markdown>=3.7",
]
```

Add gradio as optional dependency:

```toml
[project.optional-dependencies]
gradio = ["gradio>=5.0"]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-httpx>=0.30",
    "respx>=0.22",
    "ruff>=0.8",
]
```

- [ ] **Step 5: Update Dockerfile**

```dockerfile
FROM python:3.12-slim

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY apps/ ./apps/

# Install dependencies into system python (no venv inside container)
RUN uv pip install --system --no-cache .

ENV PYTHONUNBUFFERED=1 \
    SUBPRIME_DATA_DIR=/app/state/data \
    SUBPRIME_CONVERSATIONS_DIR=/app/state/conversations

# Ensure state dirs exist (volume mounts will overlay /app/state at runtime)
RUN mkdir -p /app/state/data /app/state/conversations

EXPOSE 8091

CMD ["uvicorn", "apps.web.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8091"]
```

- [ ] **Step 6: Update CLI web command**

Replace the `web` command in `src/subprime/cli.py` (lines 355-381):

```python
@app.command()
def web(
    port: int = typer.Option(
        8091,
        "--port",
        "-P",
        help="Port for the web server.",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Host to bind to.",
    ),
) -> None:
    """Launch the FinAdvisor web interface."""
    import sys

    # Ensure the project root (where apps/ lives) is on sys.path
    _project_root = str(Path(__file__).resolve().parent.parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    import uvicorn

    _console.print(f"[bold]FinAdvisor[/bold] starting at http://{host}:{port}")
    uvicorn.run("apps.web.main:create_app", factory=True, host=host, port=port)
```

- [ ] **Step 7: Update tests/test_functional.py — fix Gradio references**

The existing `test_functional.py` has Gradio web app tests. Update the import in those tests from `apps.web.app` to `apps.web.gradio_app`, or mark them as requiring the gradio optional dependency. The simplest fix:

Find `from apps.web.app import` and replace with `from apps.web.gradio_app import` in `tests/test_functional.py`.

- [ ] **Step 8: Install new dependencies and run full test suite**

```bash
cd /home/agent/projects/subprime && uv pip install --system -e ".[dev]"
python -m pytest tests/test_web_wizard.py -v
```

Expected: All PASS

- [ ] **Step 9: Run existing tests to check for regressions**

```bash
cd /home/agent/projects/subprime && python -m pytest tests/ -v --timeout=30
```

Expected: All PASS (or pre-existing failures unrelated to this change)

- [ ] **Step 10: Commit**

```bash
git add apps/web/gradio_app.py pyproject.toml Dockerfile src/subprime/cli.py tests/test_functional.py tests/test_web_wizard.py
git rm apps/web/app.py 2>/dev/null; true
git commit -m "feat(web): wire FastAPI app — update deps, Dockerfile, CLI, rename Gradio app"
```

---

### Task 8: Smoke Test — Manual Verification

**Files:** None (manual testing)

- [ ] **Step 1: Start the web server**

```bash
cd /home/agent/projects/subprime && python -m uvicorn apps.web.main:create_app --factory --port 8091
```

- [ ] **Step 2: Verify wizard flow in browser**

Open `http://localhost:8091` and verify:
1. Redirects to `/step/1` with Basic and Premium cards
2. Click "Start Free Plan" → navigates to `/step/2` with persona cards and custom form tab
3. Click a persona card → navigates to `/step/3` with loading spinner, then strategy dashboard
4. Donut chart renders correctly
5. Type feedback in chat input, press Enter → strategy updates
6. Click "Generate My Plan" → navigates to `/step/4` with full results
7. Corpus bar chart renders
8. Fund allocation rows expand to show rationale
9. Collapsible sections (risks, getting started, rebalancing) work
10. "Start Over" returns to `/step/1`

- [ ] **Step 3: Test custom profile form**

1. Go to Step 2, switch to "Custom Profile" tab
2. Fill in all fields, submit
3. Verify it proceeds to Step 3 with strategy generation

- [ ] **Step 4: Test premium mode**

1. Start over, select "Start Premium Plan"
2. Pick a persona → strategy → generate plan
3. Verify premium sections (SIP step-up, allocation timeline) appear if the model produces them

- [ ] **Step 5: Commit any fixes from manual testing**

```bash
git add -A
git commit -m "fix(web): adjustments from manual smoke testing"
```
