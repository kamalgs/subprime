# FinAdvisor Web UI Redesign — Multi-Step Wizard

## Goal

Replace the Gradio chat-only interface with a multi-step wizard built on FastAPI + Jinja2 + HTMX + Tailwind CSS. Separate basic/premium tier selection as the entry point. Use standard UI widgets (forms, cards, charts) for structured interactions and reserve chat for the one place where free-form user input matters (strategy feedback). Give the LLM's commentary dedicated rendered content areas rather than constraining it to chat bubbles or table cells.

## Architecture

**Stack**: FastAPI (async), Jinja2 templates, HTMX (partial page swaps), Tailwind CSS (CDN), Chart.js (CDN). No JS build pipeline. All Python + HTML.

**Dependency flow**: The existing `subprime` package (`advisor.planner`, `advisor.profile`, `core.models`, `evaluation.personas`, `data.*`) remains untouched. The new web app imports from it the same way the old Gradio app did.

**Deployment**: Same Dockerfile pattern — `uvicorn apps.web.main:app`. Same Nomad job with updated entrypoint.

## File Structure

```
apps/web/
├── main.py              # FastAPI app factory, middleware, static/template config
├── routes.py            # Page routes (GET /step/1, /step/2, etc.)
├── api.py               # HTMX API endpoints (POST /api/select-persona, etc.)
├── session.py           # SessionStore protocol + InMemorySessionStore
├── rendering.py         # HTML rendering helpers (INR formatting, markdown, charts data)
├── templates/
│   ├── base.html        # Layout: head (Tailwind/HTMX/Chart.js CDN), nav, step indicator, footer
│   ├── step_plan.html   # Step 1: Basic vs Premium tier selection
│   ├── step_profile.html # Step 2: Persona cards + custom profile form
│   ├── step_strategy.html # Step 3: Strategy dashboard + chat feedback area
│   ├── step_result.html  # Step 4: Full plan results page
│   └── partials/
│       ├── strategy_dashboard.html  # Strategy donut chart + themes + rationale
│       ├── strategy_chat.html       # Chat message partial for strategy feedback
│       ├── plan_stats.html          # Stat cards row (funds, SIP, returns)
│       ├── plan_allocations.html    # Fund allocation table with expandable rationales
│       ├── plan_corpus.html         # Corpus projection chart + table
│       ├── plan_commentary.html     # "Why This Plan" narrative block
│       ├── loading.html             # Skeleton/spinner partial for long operations
│       └── persona_card.html        # Single persona card (reusable)
├── static/
│   ├── app.css          # Custom styles beyond Tailwind utilities
│   └── charts.js        # Chart.js initialization (donut, bar chart helpers)
└── __init__.py
```

## Wizard Flow

### Step 1: Choose Your Plan

Full page. Two cards side by side:

**Basic (Free)**:
- "Get a solid investment plan"
- Feature list: personalised fund selection, corpus projections, risk analysis
- Blue CTA button: "Start Free Plan"

**Premium**:
- "Multiple expert perspectives compared"
- Feature list: 3-5 strategic viewpoints generated in parallel, AI evaluator picks the best, SIP step-up schedules, allocation phase timeline
- Gold-accented CTA button: "Start Premium Plan"
- Paywall hook: a `data-tier="premium"` attribute on the card. For now both are accessible. Later, the CTA can trigger a payment flow or gate.

Clicking either card sets the `mode` in the session and navigates to Step 2.

### Step 2: Tell Us About You

Two tabs (or toggle):

**Quick Start** — Grid of persona cards (P01-P08). Each card shows: name, age, risk level badge (conservative/moderate/aggressive with colour), monthly SIP, horizon, key goals. Clicking a card selects it (visual highlight), then a "Continue" CTA submits.

**Custom Profile** — Structured form with:
- Name (text input)
- Age (number input)
- Monthly SIP budget (number input, with ₹ prefix)
- Existing corpus (number input, with ₹ prefix)
- Risk appetite (3 radio buttons: conservative / moderate / aggressive, styled as selectable cards)
- Investment horizon (range slider, 1-40 years, with live label)
- Financial goals (checkbox group: retirement, children's education, house purchase, wealth building, emergency fund, other)
- Life stage (dropdown: student, early career, mid career, pre-retirement, retired)
- Additional preferences (optional textarea)
- "Continue" CTA button

Form validation: client-side HTML5 validation (required fields, min/max). Server-side Pydantic validation on submit.

### Step 3: Review Strategy

Server generates a `StrategyOutline` via `generate_strategy()`. Page renders:

**Strategy dashboard** (top area):
- Asset allocation donut chart (Chart.js) — equity / debt / gold / other segments with percentages
- Key themes as styled tag pills
- Equity approach in an info panel
- Risk/return summary card

**Model commentary area** (middle):
- "Strategy Rationale" — rendered markdown block. The model gets space to explain the reasoning in 2-3 paragraphs. Not constrained to one-liners. Rendered with paragraph breaks, bullets, bold as the model sees fit.
- Open questions (if any) as a callout box

**Strategy feedback section** (bottom):
- A compact chat-style input: "Want to adjust anything? Tell me what to change."
- When the user types feedback, `hx-post="/api/revise-strategy"` sends it, the server calls `generate_strategy(feedback=...)`, and the dashboard partial swaps in with the revised strategy. The user's message and the model's response appear as a small conversation thread above the input.
- "Looks good — generate my plan" CTA button. This is the primary action.

This is the **only place** chat appears in the entire flow.

### Step 4: Your Investment Plan

Rich results page. No chat. Entirely rendered content.

**Stat cards row**: Horizontal flex of stat boxes:
- Number of funds
- Number of fund houses
- Total monthly SIP (₹ in lakhs)
- Bear / Base / Bull CAGR %

**Corpus projection** (if SIP + horizon available):
- Grouped bar chart (Chart.js) — three bars (bear/base/bull) showing future value
- Table below with: scenario, CAGR, future value, today's ₹ (inflation-adjusted)
- Caption showing SIP amount and horizon

**Fund allocations table**:
- Columns: fund name + house + AMFI code, allocation %, mode, SIP/mo, expense ratio, rating stars
- Each row is expandable (click or chevron) to reveal the model's rationale for picking that fund — rendered as a markdown paragraph, not a truncated string

**"Why This Plan" narrative**:
- Dedicated section with a heading. The model's rationale rendered as full markdown — paragraphs, bullets, emphasis. This is where the model connects the plan to the investor's specific situation, goals, age, risk level. No length constraint beyond what the model naturally produces.

**Collapsible sections** (using `<details>`/`<summary>` or HTMX toggle):
- Risks — bullet list, plain language
- Getting Started — step-by-step setup instructions
- Rebalancing Guidelines — when and how to adjust

**Premium-only sections** (shown only in premium mode):
- SIP Step-Up schedule — simple table showing year-by-year SIP increases
- Allocation Phase Timeline — table or timeline visual showing how asset mix shifts over the horizon

**Disclaimer**: Fixed at bottom of plan section. Italicised, muted colour.

**Actions**:
- "Start Over" button — clears session, returns to Step 1
- "Download PDF" button — placeholder for future (disabled, greyed out, "Coming soon" tooltip)

## Session Management

### SessionStore Protocol

```python
from typing import Protocol

class SessionStore(Protocol):
    async def get(self, session_id: str) -> Session | None: ...
    async def save(self, session: Session) -> None: ...
    async def list_sessions(self, limit: int = 20) -> list[SessionSummary]: ...
```

### Session Model

```python
class Session(BaseModel):
    id: str                          # UUID
    created_at: datetime
    updated_at: datetime
    current_step: int = 1            # 1-4
    mode: Literal["basic", "premium"] = "basic"
    profile: InvestorProfile | None = None
    strategy: StrategyOutline | None = None
    plan: InvestmentPlan | None = None
    strategy_chat: list[ConversationTurn] = []

class SessionSummary(BaseModel):
    id: str
    investor_name: str | None = None
    mode: str
    current_step: int
    created_at: datetime
    updated_at: datetime
```

### First Implementation: InMemorySessionStore

Dict-backed. Session ID stored in a cookie (`finadvisor_session`). New session created on first visit. The interface is designed so a DuckDB/SQLite/Redis implementation can be swapped in by implementing the same protocol — no code changes in routes or API.

## HTMX Interaction Pattern

| User Action | HTMX Call | Server Response |
|---|---|---|
| Click tier card | `hx-post="/api/select-tier"` | Set session mode, `HX-Redirect` to `/step/2` |
| Click persona card | `hx-post="/api/select-persona"` | Save profile, redirect to `/step/3` |
| Submit custom form | `hx-post="/api/submit-profile"` | Validate, save profile, redirect to `/step/3` |
| Step 3 page loads | `hx-get="/api/generate-strategy" hx-trigger="load"` | Generate strategy, swap in dashboard partial |
| Send strategy feedback | `hx-post="/api/revise-strategy"` | Revise strategy, swap dashboard + append chat message |
| Click "Generate Plan" | `hx-post="/api/generate-plan"` | Generate plan, redirect to `/step/4` |
| Click "Start Over" | `hx-post="/api/reset"` | Clear session, redirect to `/step/1` |

**Loading states**: Long LLM operations (strategy generation: ~5-10s, plan generation: ~10-30s) show a skeleton loader in the HTMX swap target. Uses `hx-indicator` to show a spinner, and the partial returned includes the skeleton that auto-replaces when the real content arrives.

For plan generation specifically (which can take 30s+ in premium mode), use HTMX's `hx-get` polling pattern or SSE: the POST kicks off generation, immediately returns a "generating..." partial with a progress message, and an `hx-get="/api/plan-status"` with `hx-trigger="every 2s"` polls until the plan is ready, then swaps in the full result.

## Visual Design

**Tailwind theme**:
- Primary: `indigo-600` (buttons, links, active states)
- Text: `slate-700` body, `slate-900` headings
- Background: `gray-50` page, `white` cards
- Accent: `green-600` bull, `amber-500` base, `red-500` bear
- Premium accent: `amber-400` / `yellow-500` for premium badge/border

**Step indicator**: Horizontal bar across top of content area. Four steps with labels. Completed = indigo circle with checkmark. Current = indigo filled circle with number. Future = gray outline circle with number. Connected by lines.

**Cards**: `rounded-lg shadow-sm border border-gray-200 bg-white p-6`. Hover: `shadow-md` transition. Interactive cards get `cursor-pointer` and a subtle border colour change on hover.

**Model commentary rendering**: The model's text (rationale, fund explanations, risk descriptions) is rendered from the Pydantic model string fields. Use a simple markdown-to-HTML converter (Python `markdown` library or a minimal custom converter for bold/bullets/paragraphs) in the `rendering.py` module. Rendered inside styled `div` blocks with good typography: `text-base leading-relaxed text-slate-700`.

**Charts**:
- Donut chart (Step 3): equity/debt/gold/other segments. Legend below. Tailwind-matching colours.
- Bar chart (Step 4): grouped bars for bear/base/bull corpus projections. Labels in ₹ lakhs/crores.
- Both initialised via a small `charts.js` file that reads data from `data-*` attributes on the chart canvas element.

**Responsive**: Tailwind breakpoints. Cards go from 2-column grid to single column on mobile. Tables become stacked cards on small screens via `@media` or Tailwind responsive utilities.

## What Changes in Existing Code

**Nothing in `src/subprime/`**. The new web app imports the same functions:
- `generate_strategy()`, `generate_plan()` from `advisor.planner`
- `load_personas()` from `evaluation.personas`
- All models from `core.models`

**`apps/web/app.py`** (old Gradio app): Rename to `apps/web/gradio_app.py` to avoid confusion. The new app lives in `apps/web/main.py`. The CLI `web` command switches to launch the FastAPI app.

**`pyproject.toml`**: Replace `gradio>=5.0` with `fastapi>=0.115`, `uvicorn>=0.34`, `jinja2>=3.1`, `python-multipart>=0.0.12` (for form handling), `markdown>=3.7` (for model text rendering). Keep `gradio` as an optional dependency if desired.

**`Dockerfile`**: Change entrypoint from Gradio launch to `uvicorn apps.web.main:app --host 0.0.0.0 --port 8091`.

**`cli.py`**: Update the `web` command to launch uvicorn instead of Gradio.

## Testing

**E2E smoke tests** (Playwright or httpx test client):
- App starts without error
- GET `/` redirects to `/step/1`
- GET `/step/1` returns 200 with both tier cards
- POST `/api/select-tier` sets session mode, redirects
- GET `/step/2` shows persona cards and custom form
- POST `/api/select-persona` with valid persona ID saves profile
- POST `/api/submit-profile` with valid form data saves profile
- Full flow: select tier → select persona → generate strategy → approve → generate plan → step 4 renders

**Unit tests**:
- `rendering.py`: INR formatting, markdown rendering, chart data helpers
- `session.py`: InMemorySessionStore CRUD operations, session lifecycle
- Form validation edge cases

**Integration tests** (mock LLM calls):
- Strategy generation flow with mocked `generate_strategy()`
- Plan generation flow with mocked `generate_plan()`
- Strategy revision with feedback

## Not In Scope (First Version)

- Paywall / payment gate (just the card layout is ready for it)
- Session persistence beyond in-memory (protocol is ready)
- Session resume / session list UI (store interface supports it)
- PDF export (placeholder button only)
- User accounts / authentication
- Real-time streaming of LLM output (use polling pattern instead)
