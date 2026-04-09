# M1: Interactive Advisor — Design Spec

## Goal

Add a three-phase interactive advisor flow: profile gathering → strategy co-creation → detailed plan generation. The command `subprime advise` becomes the "show people" entry point.

## Constraints

- No new modules or dependency changes. Grows the existing advisor module + CLI.
- Core returns structured data. CLI is the UI layer (Rich console I/O).
- Advisor is concise — presents conclusions, reasons silently, doesn't overwhelm.
- All existing M0 functionality (experiments, evaluation, bulk mode) unchanged.

---

## File Map

```
MODIFY  src/subprime/advisor/agent.py       — add create_strategy_advisor()
MODIFY  src/subprime/advisor/planner.py     — add generate_strategy(), enhance generate_plan()
NEW     src/subprime/advisor/profile.py     — hybrid profile gathering
MODIFY  src/subprime/advisor/prompts/base.md — concise tone, silent reasoning
NEW     src/subprime/advisor/prompts/strategy.md — strategy-only prompt
MODIFY  src/subprime/advisor/__init__.py    — export new symbols
MODIFY  src/subprime/core/display.py        — add format_strategy_outline()
MODIFY  src/subprime/cli.py                 — add advise command
```

---

## Phase 1: Profile Gathering

### `advisor/profile.py`

**Approach:** Hybrid — open prompt with nudges for missing fields.

**Core function:**
```python
async def gather_profile(
    send_message: Callable[[str], Awaitable[str]],
    existing_profile: InvestorProfile | None = None,
    prompt_hooks: dict[str, str] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> InvestorProfile:
```

- `send_message` is a callback: takes agent's question (str), returns user's response (str). This decouples the advisor logic from the UI layer — CLI passes a Rich prompt implementation, tests pass a mock.
- If `existing_profile` is provided, returns it immediately (bulk mode bypass).
- Otherwise, runs a multi-turn conversation loop.

**Profile agent:**
- PydanticAI agent with a system prompt that lists required InvestorProfile fields.
- Agent opens with a brief invitation: "Tell me about your investment goals and financial situation — age, income, risk comfort, time horizon, and what you're investing for."
- After each user response, agent attempts to extract an InvestorProfile. If fields are missing, it nudges: "Got it. What's your approximate monthly investible surplus in INR?"
- Loop ends when all required fields are populated.
- Agent confirms with a brief summary: "Here's what I have: [summary]. Shall I proceed?"

**Implementation detail:** The profile agent doesn't use `output_type=InvestorProfile` directly (multi-turn conversation doesn't map to single structured output). Instead, after the conversation, a separate extraction call with `output_type=InvestorProfile` parses the full conversation into a structured profile.

### `advisor/prompts/profile.md` (NEW)

System prompt for the profile gathering agent:
- List all InvestorProfile fields with brief descriptions
- Instruct: open with a broad question, extract what you can, nudge for gaps
- Tone: brief, friendly, no jargon, no verbose explanations
- Indian context: amounts in INR (lakhs/crores), tax regime (old/new), common goals (children's education, retirement corpus, house down payment)

---

## Phase 2: Strategy Co-creation

### `advisor/planner.py` — new function

```python
async def generate_strategy(
    profile: InvestorProfile,
    feedback: str | None = None,
    current_strategy: StrategyOutline | None = None,
    prompt_hooks: dict[str, str] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> StrategyOutline:
```

- First call: `feedback=None, current_strategy=None` → agent proposes fresh strategy.
- Revision calls: `feedback="more equity, less debt", current_strategy=<previous>` → agent revises.
- Returns `StrategyOutline` (structured data, no fund names).

### `advisor/agent.py` — new factory

```python
def create_strategy_advisor(
    prompt_hooks: dict[str, str] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> Agent:
```

- System prompt: base.md + strategy.md + optional philosophy hook.
- `output_type=StrategyOutline`
- No tools registered (no fund lookups in strategy phase).
- retries=2

### `advisor/prompts/strategy.md` (NEW)

Instructions for strategy-only generation:
- Propose high-level allocation: equity %, debt %, gold %, other %
- State the equity approach (index-heavy, active mix, sector tilt, etc.)
- List key themes (tax efficiency, low cost, growth tilt, etc.)
- Provide a one-line risk/return summary
- List open questions if the situation is ambiguous
- Be brief — this is a direction check, not a full plan
- No fund names, no AMFI codes, no SIP amounts

---

## Phase 3: Plan Generation (enhanced)

### `advisor/planner.py` — modify generate_plan()

```python
async def generate_plan(
    profile: InvestorProfile,
    strategy: StrategyOutline | None = None,  # NEW parameter
    prompt_hooks: dict[str, str] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> InvestmentPlan:
```

- If `strategy` is provided, include it in the user prompt: "The investor has approved this strategy direction: {strategy JSON}. Now select specific mutual fund schemes that implement this strategy."
- If `strategy` is None, behaves as before (agent decides everything).
- Tool calls happen here: search_funds, get_fund_performance, compare_funds.

---

## CLI: `subprime advise`

### Command signature

```
subprime advise [--profile ID] [--model MODEL]
```

- `--profile P01`: Load persona from bank, skip Phase 1. Go to Phase 2.
- No `--profile`: Interactive Phase 1 → 2 → 3.

### Orchestration (in cli.py)

```python
@app.command()
def advise(profile_id: str | None, model: str):
    # Phase 1: Profile
    if profile_id:
        profile = get_persona(profile_id)
    else:
        profile = asyncio.run(gather_profile(send_message=rich_prompt))

    # Phase 2: Strategy loop
    strategy = asyncio.run(generate_strategy(profile, model=model))
    display(format_strategy_outline(strategy))
    while True:
        response = Prompt.ask("Ready to find specific funds? (yes / tell me what to adjust)")
        if response.lower() in ("yes", "y"):
            break
        strategy = asyncio.run(generate_strategy(profile, feedback=response, current_strategy=strategy, model=model))
        display(format_strategy_outline(strategy))

    # Phase 3: Plan
    plan = asyncio.run(generate_plan(profile, strategy=strategy, model=model))
    display(format_plan_summary(plan))
```

### `rich_prompt` callback for Phase 1

```python
async def rich_prompt(message: str) -> str:
    console.print(f"\n[bold]{message}[/bold]")
    return Prompt.ask(">")
```

---

## Display

### `core/display.py` — add format_strategy_outline()

```python
def format_strategy_outline(outline: StrategyOutline) -> str:
```

Renders:
- Allocation split as a compact table (Equity X% | Debt Y% | Gold Z%)
- Equity approach (one line)
- Key themes (bullet list)
- Risk/return summary (one line)
- Open questions (if any)

---

## Prompt Tone Updates

### `advisor/prompts/base.md` — add to existing

Append:
```
Be concise. Present your recommendations and conclusions — do not explain your reasoning process out loud. Keep responses brief and scannable. If the investor asks "why", then explain. Otherwise, state what you recommend and move on.
```

---

## Testing

### Small tests (mock LLM, fast, deterministic)

**test_advisor/test_profile.py:**
- `gather_profile` with `existing_profile` returns it immediately (bulk bypass)
- `gather_profile` with mocked send_message + mocked LLM extracts profile from conversation
- Profile agent prompt contains required field names

**test_advisor/test_planner.py (additions):**
- `generate_strategy` with mocked LLM returns StrategyOutline
- `generate_strategy` with feedback passes feedback to agent
- `generate_plan` with strategy includes strategy in user prompt
- `generate_plan` without strategy works as before (backward compatible)

**test_core/test_display.py (additions):**
- `format_strategy_outline` returns string with equity/debt/gold percentages
- `format_strategy_outline` includes themes and approach

**test_cli.py (additions):**
- `advise --help` shows expected options
- `advise --profile P01` with mocked advisor runs without error

### Medium tests (integration)

**test_integration.py (additions):**
- Full three-phase wiring: load persona → generate_strategy (mocked) → generate_plan (mocked) → display
- Strategy revision loop with mocked feedback
