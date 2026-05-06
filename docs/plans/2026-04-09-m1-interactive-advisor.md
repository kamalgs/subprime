# M1: Interactive Advisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a three-phase interactive advisor (`subprime advise`): hybrid profile gathering → strategy co-creation with explicit approval → detailed plan generation with real fund data.

**Architecture:** Grows the existing advisor module with profile.py (Phase 1), strategy prompt + generate_strategy (Phase 2), and enhanced generate_plan accepting a StrategyOutline (Phase 3). CLI orchestrates the three phases with Plain Rich I/O. Core returns structured data; CLI is the UI layer.

**Tech Stack:** PydanticAI, Rich (Prompt.ask, Console.print), Typer, existing mfdata.in tools

**Spec:** `docs/superpowers/specs/2026-04-09-m1-interactive-advisor-design.md`

---

### Task 1: Update base.md prompt tone

**Files:**
- Modify: `src/subprime/advisor/prompts/base.md`
- Test: `tests/test_advisor/test_planner.py` (existing test verifies content)

- [ ] **Step 1: Update base.md to add concise tone instructions**

Append to the end of `src/subprime/advisor/prompts/base.md`:

```markdown

Be concise. Present your recommendations and conclusions — do not explain your reasoning process out loud. Keep responses brief and scannable. If the investor asks "why", then explain. Otherwise, state what you recommend and move on.
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
uv run pytest tests/test_advisor/test_planner.py -v
```

Expected: All existing tests PASS (prompt still contains "financial advisor" and "Indian").

- [ ] **Step 3: Commit**

```bash
git add src/subprime/advisor/prompts/base.md
git commit -m "feat(advisor): add concise tone instructions to base prompt"
```

---

### Task 2: Add strategy prompt and strategy advisor factory

**Files:**
- Create: `src/subprime/advisor/prompts/strategy.md`
- Create: `src/subprime/advisor/prompts/profile.md`
- Modify: `src/subprime/advisor/agent.py`
- Test: `tests/test_advisor/test_strategy.py`

- [ ] **Step 1: Write src/subprime/advisor/prompts/strategy.md**

```markdown
Propose a high-level investment strategy for the investor. Do not name specific funds or AMFI codes — just the direction.

Output:
- Asset allocation: equity %, debt %, gold %, other %
- Equity approach: e.g. "index-heavy", "active mid/small cap tilt", "balanced mix"
- Key themes: e.g. "tax efficiency under 80C", "low cost", "growth tilt", "capital preservation"
- One-line risk/return summary
- Open questions: anything ambiguous about the investor's situation that would change the strategy

Be brief. This is a direction check before selecting specific funds.
```

- [ ] **Step 2: Write src/subprime/advisor/prompts/profile.md**

```markdown
You are gathering an investor's profile through conversation. You need these details:

Required:
- Name and age
- Risk appetite (conservative / moderate / aggressive)
- Investment horizon in years
- Monthly investible surplus in INR
- Existing investment corpus in INR
- Liabilities in INR
- Financial goals (specific amounts and timeframes)
- Life stage (early career, mid career, pre-retirement, retired)
- Tax regime (old / new)

Optional:
- Preferences (e.g. "no sectoral funds", "SIP only", "interested in pharma sector")

Start with a brief, open invitation — let the investor describe their situation in their own words. Extract what you can from their response. Then ask targeted follow-up questions for any missing required fields. Use INR with lakhs/crores notation. Be brief and friendly.

When you have all required fields, confirm with a short summary and ask if anything needs correction.
```

- [ ] **Step 3: Write the test file**

```python
"""Tests for strategy advisor factory and strategy prompt."""
from __future__ import annotations

from subprime.advisor.agent import create_strategy_advisor, load_prompt


def test_load_prompt_strategy():
    prompt = load_prompt("strategy")
    assert "asset allocation" in prompt.lower() or "allocation" in prompt.lower()
    assert "fund" in prompt.lower()


def test_load_prompt_profile():
    prompt = load_prompt("profile")
    assert "risk appetite" in prompt.lower()
    assert "monthly" in prompt.lower()


def test_create_strategy_advisor_default():
    agent = create_strategy_advisor()
    assert agent is not None


def test_create_strategy_advisor_no_tools():
    """Strategy advisor should have NO tools — no fund lookups yet."""
    agent = create_strategy_advisor()
    assert len(agent._function_toolset.tools) == 0


def test_create_strategy_advisor_with_hook():
    agent = create_strategy_advisor(prompt_hooks={"philosophy": "Always prefer index funds."})
    assert agent is not None


def test_create_strategy_advisor_hook_in_prompt():
    hook_text = "STRATEGY_TEST_MARKER"
    agent = create_strategy_advisor(prompt_hooks={"philosophy": hook_text})
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "STRATEGY_TEST_MARKER" in combined


def test_create_strategy_advisor_baseline_no_philosophy():
    agent = create_strategy_advisor()
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "Investment Philosophy" not in combined
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
uv run pytest tests/test_advisor/test_strategy.py -v
```

Expected: FAIL — `create_strategy_advisor` not importable.

- [ ] **Step 5: Add create_strategy_advisor to agent.py**

Add this function to `src/subprime/advisor/agent.py` after the existing `create_advisor` function:

```python
def create_strategy_advisor(
    prompt_hooks: dict[str, str] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> Agent:
    """Create a strategy-only advisor (no fund lookups, no tools).

    Used in Phase 2 of the interactive flow — proposes high-level
    asset allocation before selecting specific funds.
    """
    base = load_prompt("base")
    strategy = load_prompt("strategy")

    philosophy = ""
    if prompt_hooks and "philosophy" in prompt_hooks:
        philosophy = prompt_hooks["philosophy"]
    else:
        hook_path = _PROMPTS_DIR / "hooks" / "philosophy.md"
        if hook_path.exists():
            philosophy = hook_path.read_text().strip()

    parts = [base, strategy]
    if philosophy:
        parts.append(f"## Investment Philosophy\n\n{philosophy}")

    system_prompt = "\n\n---\n\n".join(parts)

    return Agent(
        model,
        system_prompt=system_prompt,
        output_type=StrategyOutline,
        tools=[],
        retries=2,
        defer_model_check=True,
    )
```

Also add the import at the top of `agent.py`:
```python
from subprime.core.models import InvestmentPlan, StrategyOutline
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/test_advisor/test_strategy.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 7: Run full suite**

```bash
uv run pytest -q
```

Expected: All tests PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add src/subprime/advisor/prompts/strategy.md src/subprime/advisor/prompts/profile.md src/subprime/advisor/agent.py tests/test_advisor/test_strategy.py
git commit -m "feat(advisor): add strategy advisor factory and profile/strategy prompts"
```

---

### Task 3: Add generate_strategy to planner

**Files:**
- Modify: `src/subprime/advisor/planner.py`
- Modify: `src/subprime/advisor/__init__.py`
- Test: `tests/test_advisor/test_strategy.py` (add to existing)

- [ ] **Step 1: Add strategy tests to test_strategy.py**

Append to `tests/test_advisor/test_strategy.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from subprime.core.models import InvestorProfile, StrategyOutline


@pytest.fixture
def sample_profile():
    return InvestorProfile(
        id="P01",
        name="Arjun Mehta",
        age=25,
        risk_appetite="aggressive",
        investment_horizon_years=30,
        monthly_investible_surplus_inr=50000,
        existing_corpus_inr=200000,
        liabilities_inr=0,
        financial_goals=["Retire by 55 with 10Cr corpus"],
        life_stage="Early career",
        tax_bracket="new_regime",
    )


def _make_fake_strategy() -> StrategyOutline:
    return StrategyOutline(
        equity_pct=70.0,
        debt_pct=20.0,
        gold_pct=10.0,
        other_pct=0.0,
        equity_approach="Index-heavy with small active tilt",
        key_themes=["low cost", "broad diversification", "tax efficiency"],
        risk_return_summary="Targeting 12-14% CAGR with moderate volatility",
        open_questions=[],
    )


@pytest.mark.asyncio
async def test_generate_strategy(sample_profile):
    from subprime.advisor.planner import generate_strategy

    fake_strategy = _make_fake_strategy()
    mock_result = MagicMock()
    mock_result.output = fake_strategy

    with patch("subprime.advisor.planner.create_strategy_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        strategy = await generate_strategy(sample_profile)

    assert isinstance(strategy, StrategyOutline)
    assert strategy.equity_pct == 70.0
    assert "low cost" in strategy.key_themes


@pytest.mark.asyncio
async def test_generate_strategy_with_feedback(sample_profile):
    from subprime.advisor.planner import generate_strategy

    fake_strategy = _make_fake_strategy()
    mock_result = MagicMock()
    mock_result.output = fake_strategy

    current = _make_fake_strategy()

    with patch("subprime.advisor.planner.create_strategy_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        strategy = await generate_strategy(
            sample_profile,
            feedback="More equity, less debt",
            current_strategy=current,
        )

    # Verify the agent was called with feedback in the prompt
    call_args = mock_agent.run.call_args
    user_prompt = call_args[0][0]
    assert "More equity, less debt" in user_prompt
    assert isinstance(strategy, StrategyOutline)


@pytest.mark.asyncio
async def test_generate_strategy_passes_hooks(sample_profile):
    from subprime.advisor.planner import generate_strategy

    fake_strategy = _make_fake_strategy()
    mock_result = MagicMock()
    mock_result.output = fake_strategy

    hooks = {"philosophy": "Prefer index funds."}

    with patch("subprime.advisor.planner.create_strategy_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        await generate_strategy(sample_profile, prompt_hooks=hooks)

    mock_create.assert_called_once_with(prompt_hooks=hooks, model="anthropic:claude-sonnet-4-6")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_advisor/test_strategy.py::test_generate_strategy -v
```

Expected: FAIL — `generate_strategy` not importable.

- [ ] **Step 3: Add generate_strategy to planner.py**

Add to `src/subprime/advisor/planner.py`:

```python
from subprime.advisor.agent import create_advisor, create_strategy_advisor
from subprime.core.models import InvestmentPlan, InvestorProfile, StrategyOutline


async def generate_strategy(
    profile: InvestorProfile,
    feedback: str | None = None,
    current_strategy: StrategyOutline | None = None,
    prompt_hooks: dict[str, str] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> StrategyOutline:
    """Generate or revise a high-level investment strategy.

    First call (no feedback/current_strategy): proposes a fresh strategy.
    Revision calls: incorporates feedback to adjust the current strategy.
    """
    agent = create_strategy_advisor(prompt_hooks=prompt_hooks, model=model)

    parts = [
        f"Investor profile:\n\n{profile.model_dump_json(indent=2)}"
    ]

    if current_strategy and feedback:
        parts.append(
            f"\nCurrent strategy:\n\n{current_strategy.model_dump_json(indent=2)}"
            f"\n\nInvestor feedback: {feedback}"
            f"\n\nRevise the strategy based on this feedback."
        )
    elif current_strategy:
        parts.append(
            f"\nCurrent strategy:\n\n{current_strategy.model_dump_json(indent=2)}"
            f"\n\nRefine this strategy."
        )

    result = await agent.run("\n".join(parts))
    return result.output
```

Also update `generate_plan` to accept an optional strategy:

```python
async def generate_plan(
    profile: InvestorProfile,
    strategy: StrategyOutline | None = None,
    prompt_hooks: dict[str, str] | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> InvestmentPlan:
    """Generate an investment plan for the given investor profile.

    Args:
        profile: Complete investor profile.
        strategy: Optional approved strategy to guide fund selection.
        prompt_hooks: Optional philosophy injection for experiments.
        model: LLM model identifier.
    """
    agent = create_advisor(prompt_hooks=prompt_hooks, model=model)

    parts = [
        f"Create a detailed mutual fund investment plan for this investor:\n\n"
        f"{profile.model_dump_json(indent=2)}"
    ]

    if strategy:
        parts.append(
            f"\nThe investor has approved this strategy direction:\n\n"
            f"{strategy.model_dump_json(indent=2)}\n\n"
            f"Select specific mutual fund schemes that implement this strategy."
        )

    result = await agent.run("\n".join(parts))
    return result.output
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_advisor/test_strategy.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 5: Add test for generate_plan with strategy**

Append to `tests/test_advisor/test_planner.py`:

```python
@pytest.mark.asyncio
async def test_generate_plan_with_strategy(sample_profile):
    """generate_plan with a strategy should include it in the prompt."""
    from subprime.advisor.planner import generate_plan

    fake_plan = _make_fake_plan()
    mock_result = MagicMock()
    mock_result.output = fake_plan

    strategy = StrategyOutline(
        equity_pct=70.0, debt_pct=20.0, gold_pct=10.0, other_pct=0.0,
        equity_approach="Index-heavy",
        key_themes=["low cost"],
        risk_return_summary="12% CAGR target",
        open_questions=[],
    )

    with patch("subprime.advisor.planner.create_advisor") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        plan = await generate_plan(sample_profile, strategy=strategy)

    call_args = mock_agent.run.call_args
    user_prompt = call_args[0][0]
    assert "approved this strategy" in user_prompt
    assert "Index-heavy" in user_prompt
    assert isinstance(plan, InvestmentPlan)
```

Add `StrategyOutline` to the imports at the top of `test_planner.py`:
```python
from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
    StrategyOutline,
)
```

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest -q
```

Expected: All tests PASS, no regressions. The existing `test_generate_plan` still passes because `strategy` defaults to `None`.

- [ ] **Step 7: Update advisor/__init__.py exports**

```python
"""Advisor module — financial advisor agent, prompts, planning."""
from subprime.advisor.agent import create_advisor, create_strategy_advisor, load_prompt
from subprime.advisor.planner import generate_plan, generate_strategy

__all__ = [
    "create_advisor",
    "create_strategy_advisor",
    "generate_plan",
    "generate_strategy",
    "load_prompt",
]
```

- [ ] **Step 8: Commit**

```bash
git add src/subprime/advisor/ tests/test_advisor/
git commit -m "feat(advisor): add generate_strategy and strategy-aware generate_plan"
```

---

### Task 4: Add profile gathering

**Files:**
- Create: `src/subprime/advisor/profile.py`
- Test: `tests/test_advisor/test_profile.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for interactive profile gathering."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from subprime.core.models import InvestorProfile


@pytest.fixture
def complete_profile():
    return InvestorProfile(
        id="interactive",
        name="Arjun Mehta",
        age=25,
        risk_appetite="aggressive",
        investment_horizon_years=30,
        monthly_investible_surplus_inr=50000,
        existing_corpus_inr=200000,
        liabilities_inr=0,
        financial_goals=["Retire by 55 with 10Cr corpus"],
        life_stage="Early career",
        tax_bracket="new_regime",
    )


@pytest.mark.asyncio
async def test_gather_profile_bulk_bypass(complete_profile):
    """If existing_profile is provided, return it immediately."""
    from subprime.advisor.profile import gather_profile

    async def mock_send(msg: str) -> str:
        raise AssertionError("send_message should not be called in bulk mode")

    result = await gather_profile(send_message=mock_send, existing_profile=complete_profile)
    assert result.name == "Arjun Mehta"
    assert result.age == 25


@pytest.mark.asyncio
async def test_gather_profile_interactive(complete_profile):
    """Interactive mode: LLM extracts profile from conversation."""
    from subprime.advisor.profile import gather_profile

    # Simulate a two-turn conversation
    responses = iter([
        "I'm Arjun, 25, working in tech. I can invest 50k per month and want to retire by 55 with 10Cr.",
        "Yes, that looks correct.",
    ])

    async def mock_send(msg: str) -> str:
        return next(responses)

    with patch("subprime.advisor.profile._run_conversation") as mock_conv:
        mock_conv.return_value = (
            "Arjun told us he is 25, aggressive risk, 30yr horizon, 50k/mo surplus...",
            complete_profile,
        )

        result = await gather_profile(send_message=mock_send)

    assert isinstance(result, InvestorProfile)
    assert result.name == "Arjun Mehta"


@pytest.mark.asyncio
async def test_gather_profile_returns_investor_profile():
    """The return type must be InvestorProfile."""
    from subprime.advisor.profile import gather_profile

    profile = InvestorProfile(
        id="test",
        name="Test",
        age=30,
        risk_appetite="moderate",
        investment_horizon_years=10,
        monthly_investible_surplus_inr=10000,
        existing_corpus_inr=0,
        liabilities_inr=0,
        financial_goals=["Save"],
        life_stage="Mid career",
        tax_bracket="new_regime",
    )

    result = await gather_profile(
        send_message=AsyncMock(),
        existing_profile=profile,
    )
    assert isinstance(result, InvestorProfile)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_advisor/test_profile.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write src/subprime/advisor/profile.py**

```python
"""Interactive profile gathering — hybrid open prompt with nudges."""
from __future__ import annotations

from typing import Awaitable, Callable

from pydantic_ai import Agent

from subprime.advisor.agent import load_prompt
from subprime.core.models import InvestorProfile


async def _run_conversation(
    send_message: Callable[[str], Awaitable[str]],
    model: str,
) -> tuple[str, InvestorProfile]:
    """Run the multi-turn profile gathering conversation.

    Returns (conversation_text, extracted_profile).
    """
    profile_prompt = load_prompt("profile")

    # Conversation agent — free-text responses, not structured output
    conv_agent = Agent(
        model,
        system_prompt=profile_prompt,
        defer_model_check=True,
    )

    opening = (
        "Tell me about your investment goals and financial situation — "
        "your age, income you can invest monthly, how long you're investing for, "
        "and what you're saving towards."
    )

    response = await send_message(opening)
    conversation = f"Investor: {response}\n"

    # Multi-turn: up to 5 rounds of follow-ups
    for _ in range(5):
        result = await conv_agent.run(
            f"Conversation so far:\n{conversation}\n\n"
            "If you have all required profile fields, respond with exactly "
            "'PROFILE_COMPLETE' followed by a summary. "
            "Otherwise, ask ONE brief follow-up question for the most important missing field."
        )
        agent_reply = result.output

        if "PROFILE_COMPLETE" in str(agent_reply):
            break

        follow_up = await send_message(str(agent_reply))
        conversation += f"Advisor: {agent_reply}\nInvestor: {follow_up}\n"

    # Extract structured profile from the conversation
    extractor = Agent(
        model,
        system_prompt=(
            "Extract an InvestorProfile from this conversation. "
            "Use 'interactive' as the id. "
            "Infer reasonable defaults for any missing optional fields."
        ),
        output_type=InvestorProfile,
        retries=2,
        defer_model_check=True,
    )

    extract_result = await extractor.run(conversation)
    return conversation, extract_result.output


async def gather_profile(
    send_message: Callable[[str], Awaitable[str]],
    existing_profile: InvestorProfile | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> InvestorProfile:
    """Gather an investor profile interactively or return an existing one.

    Args:
        send_message: Callback that displays a message and returns user input.
        existing_profile: If provided, skip Q&A and return this directly.
        model: LLM model identifier.
    """
    if existing_profile is not None:
        return existing_profile

    _, profile = await _run_conversation(send_message, model)
    return profile
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_advisor/test_profile.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Update advisor/__init__.py**

Add `gather_profile` to `src/subprime/advisor/__init__.py`:

```python
"""Advisor module — financial advisor agent, prompts, planning."""
from subprime.advisor.agent import create_advisor, create_strategy_advisor, load_prompt
from subprime.advisor.planner import generate_plan, generate_strategy
from subprime.advisor.profile import gather_profile

__all__ = [
    "create_advisor",
    "create_strategy_advisor",
    "gather_profile",
    "generate_plan",
    "generate_strategy",
    "load_prompt",
]
```

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest -q
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/subprime/advisor/ tests/test_advisor/
git commit -m "feat(advisor): add interactive profile gathering with hybrid Q&A"
```

---

### Task 5: Add format_strategy_outline to display

**Files:**
- Modify: `src/subprime/core/display.py`
- Modify: `tests/test_core/test_display.py`

- [ ] **Step 1: Add tests for format_strategy_outline**

Append to `tests/test_core/test_display.py`:

```python
from subprime.core.models import StrategyOutline


def _make_strategy() -> StrategyOutline:
    return StrategyOutline(
        equity_pct=70.0,
        debt_pct=20.0,
        gold_pct=10.0,
        other_pct=0.0,
        equity_approach="Index-heavy with small active tilt",
        key_themes=["low cost", "broad diversification", "tax efficiency under 80C"],
        risk_return_summary="Targeting 12-14% CAGR with moderate volatility",
        open_questions=["Any sector preferences?"],
    )


class TestFormatStrategyOutline:
    def test_returns_string(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert isinstance(result, str)

    def test_contains_allocation_percentages(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert "70" in result
        assert "20" in result
        assert "10" in result

    def test_contains_equity_approach(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert "Index-heavy" in result or "index" in result.lower()

    def test_contains_themes(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert "low cost" in result.lower()

    def test_contains_risk_return_summary(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert "12" in result or "CAGR" in result

    def test_contains_open_questions(self):
        from subprime.core.display import format_strategy_outline

        result = format_strategy_outline(_make_strategy())
        assert "sector" in result.lower()

    def test_no_open_questions(self):
        from subprime.core.display import format_strategy_outline

        s = _make_strategy()
        s = s.model_copy(update={"open_questions": []})
        result = format_strategy_outline(s)
        assert isinstance(result, str)  # Should not crash
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_core/test_display.py::TestFormatStrategyOutline -v
```

Expected: FAIL — `format_strategy_outline` not importable.

- [ ] **Step 3: Add format_strategy_outline to display.py**

Add to `src/subprime/core/display.py`:

```python
from subprime.core.models import APSScore, InvestmentPlan, PlanQualityScore, StrategyOutline
```

Then add the function:

```python
def format_strategy_outline(outline: StrategyOutline) -> str:
    """Render a StrategyOutline to a Rich-formatted string."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=100)

    # Allocation split
    alloc_table = Table(title="Strategy Outline", show_lines=True)
    alloc_table.add_column("Asset Class", style="bold")
    alloc_table.add_column("Allocation", justify="right")

    alloc_table.add_row("Equity", f"{outline.equity_pct:.0f}%")
    alloc_table.add_row("Debt", f"{outline.debt_pct:.0f}%")
    alloc_table.add_row("Gold", f"{outline.gold_pct:.0f}%")
    if outline.other_pct > 0:
        alloc_table.add_row("Other", f"{outline.other_pct:.0f}%")

    console.print(alloc_table)

    # Approach and themes
    console.print(f"\n[bold]Approach:[/bold] {outline.equity_approach}")
    console.print(f"[bold]Themes:[/bold] {', '.join(outline.key_themes)}")
    console.print(f"[bold]Expected:[/bold] {outline.risk_return_summary}")

    # Open questions
    if outline.open_questions:
        console.print("\n[bold yellow]Open questions:[/bold yellow]")
        for q in outline.open_questions:
            console.print(f"  - {q}")

    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_core/test_display.py -v
```

Expected: All tests PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add src/subprime/core/display.py tests/test_core/test_display.py
git commit -m "feat(core): add format_strategy_outline display helper"
```

---

### Task 6: Add `advise` CLI command

**Files:**
- Modify: `src/subprime/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add CLI tests**

Append to `tests/test_cli.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


class TestAdvise:
    def test_help_exits_zero(self):
        result = runner.invoke(app, ["advise", "--help"])
        assert result.exit_code == 0

    def test_help_shows_profile_option(self):
        result = runner.invoke(app, ["advise", "--help"])
        assert "--profile" in result.output or "-p" in result.output

    def test_help_shows_model_option(self):
        result = runner.invoke(app, ["advise", "--help"])
        assert "--model" in result.output or "-m" in result.output

    def test_advise_with_profile_bulk_mode(self):
        """--profile P01 should skip interactive Q&A and go through strategy + plan."""
        from subprime.core.models import StrategyOutline

        fake_strategy = StrategyOutline(
            equity_pct=70.0, debt_pct=20.0, gold_pct=10.0, other_pct=0.0,
            equity_approach="Index-heavy",
            key_themes=["low cost"],
            risk_return_summary="12% CAGR",
            open_questions=[],
        )

        fake_plan = InvestmentPlan(
            allocations=[
                Allocation(
                    fund=MutualFund(
                        amfi_code="120503", name="UTI Nifty 50",
                        category="Equity", sub_category="Index",
                        fund_house="UTI", nav=150.0, expense_ratio=0.18,
                    ),
                    allocation_pct=100.0, mode="sip",
                    monthly_sip_inr=50000, rationale="Core index",
                )
            ],
            setup_phase="Start SIP month 1",
            review_checkpoints=["6-month"],
            rebalancing_guidelines="Annual",
            projected_returns={"base": 12.0, "bull": 16.0, "bear": 6.0},
            rationale="Simple index strategy",
            risks=["Market risk"],
            disclaimer="Research only",
        )

        with (
            patch("subprime.cli.generate_strategy", new_callable=AsyncMock, return_value=fake_strategy),
            patch("subprime.cli.generate_plan", new_callable=AsyncMock, return_value=fake_plan),
        ):
            result = runner.invoke(app, ["advise", "--profile", "P01"], input="yes\n")

        assert result.exit_code == 0
        assert "UTI Nifty 50" in result.output or "Strategy" in result.output
```

Add these imports at the top of `test_cli.py` if not already present:
```python
from subprime.core.models import (
    APSScore,
    Allocation,
    ExperimentResult,
    InvestmentPlan,
    MutualFund,
    PlanQualityScore,
    StrategyOutline,
)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cli.py::TestAdvise -v
```

Expected: FAIL — no `advise` command.

- [ ] **Step 3: Add advise command to cli.py**

Add to `src/subprime/cli.py`:

```python
from rich.prompt import Prompt

from subprime.advisor.planner import generate_plan, generate_strategy
from subprime.core.display import format_plan_summary, format_strategy_outline


@app.command()
def advise(
    profile_id: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Persona ID from bank (e.g. P01). Skips interactive profile gathering.",
    ),
    model: str = typer.Option(
        "anthropic:claude-sonnet-4-6",
        "--model",
        "-m",
        help="LLM model identifier.",
    ),
) -> None:
    """Interactive financial advisor — gather profile, co-create strategy, generate plan."""

    # Phase 1: Profile
    if profile_id:
        from subprime.evaluation.personas import get_persona

        profile = get_persona(profile_id)
        _console.print(f"\n[bold]Using profile:[/bold] {profile.name} ({profile.id})\n")
    else:
        from subprime.advisor.profile import gather_profile

        async def _rich_prompt(message: str) -> str:
            _console.print(f"\n[bold]{message}[/bold]")
            return Prompt.ask(">")

        profile = asyncio.run(gather_profile(send_message=_rich_prompt, model=model))
        _console.print(f"\n[bold]Profile ready:[/bold] {profile.name}\n")

    # Phase 2: Strategy co-creation
    _console.print("[dim]Generating strategy...[/dim]")
    strategy = asyncio.run(generate_strategy(profile, model=model))
    _console.print(format_strategy_outline(strategy))

    while True:
        response = Prompt.ask(
            "\nReady to find specific funds? ([bold green]yes[/bold green] / tell me what to adjust)"
        )
        if response.strip().lower() in ("yes", "y"):
            break
        _console.print("[dim]Revising strategy...[/dim]")
        strategy = asyncio.run(
            generate_strategy(profile, feedback=response, current_strategy=strategy, model=model)
        )
        _console.print(format_strategy_outline(strategy))

    # Phase 3: Detailed plan
    _console.print("\n[dim]Generating detailed plan with specific funds...[/dim]")
    plan = asyncio.run(generate_plan(profile, strategy=strategy, model=model))
    _console.print(format_plan_summary(plan))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: All tests PASS (new + existing).

- [ ] **Step 5: Verify CLI shows the new command**

```bash
uv run subprime --help
uv run subprime advise --help
```

Expected: `advise` appears in command list with --profile and --model options.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest -q
```

Expected: All tests PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/subprime/cli.py tests/test_cli.py
git commit -m "feat: add 'subprime advise' CLI command with three-phase flow"
```

---

### Task 7: Integration test for the full advise flow

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Add M1 integration tests**

Append to `tests/test_integration.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


class TestM1AdvisorFlow:
    """Integration tests for the three-phase interactive advisor."""

    def test_strategy_advisor_creates_for_all_conditions(self):
        from subprime.advisor import create_strategy_advisor
        from subprime.experiments import CONDITIONS

        for cond in CONDITIONS:
            agent = create_strategy_advisor(prompt_hooks=cond.prompt_hooks)
            assert agent is not None
            # Strategy advisor should have NO tools
            assert len(agent._function_toolset.tools) == 0

    def test_strategy_advisor_different_from_plan_advisor(self):
        from subprime.advisor import create_advisor, create_strategy_advisor

        plan_agent = create_advisor()
        strategy_agent = create_strategy_advisor()

        plan_prompts = " ".join(str(s) for s in plan_agent._system_prompts)
        strategy_prompts = " ".join(str(s) for s in strategy_agent._system_prompts)

        # Plan advisor has planning.md content, strategy has strategy.md content
        assert plan_prompts != strategy_prompts
        assert len(plan_agent._function_toolset.tools) > 0
        assert len(strategy_agent._function_toolset.tools) == 0

    @pytest.mark.asyncio
    async def test_full_flow_mocked(self):
        """Full three-phase flow: profile → strategy → plan, all mocked."""
        from subprime.advisor import generate_plan, generate_strategy
        from subprime.evaluation import get_persona
        from subprime.core.display import format_strategy_outline, format_plan_summary

        profile = get_persona("P01")

        # Phase 2: Mock strategy
        fake_strategy = StrategyOutline(
            equity_pct=75.0, debt_pct=15.0, gold_pct=10.0, other_pct=0.0,
            equity_approach="Index-heavy",
            key_themes=["low cost", "broad market"],
            risk_return_summary="12-14% CAGR",
            open_questions=[],
        )
        mock_strategy_result = MagicMock()
        mock_strategy_result.output = fake_strategy

        with patch("subprime.advisor.planner.create_strategy_advisor") as mock_cs:
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=mock_strategy_result)
            mock_cs.return_value = mock_agent

            strategy = await generate_strategy(profile)

        assert strategy.equity_pct == 75.0
        strategy_display = format_strategy_outline(strategy)
        assert "75" in strategy_display

        # Phase 3: Mock plan
        fund = MutualFund(
            amfi_code="120503", name="UTI Nifty 50",
            category="Equity", sub_category="Index",
            fund_house="UTI", nav=150.0, expense_ratio=0.18,
        )
        fake_plan = InvestmentPlan(
            allocations=[
                Allocation(fund=fund, allocation_pct=75.0, mode="sip",
                           monthly_sip_inr=37500, rationale="Core index"),
            ],
            setup_phase="Start SIP month 1",
            review_checkpoints=["6-month"],
            rebalancing_guidelines="Annual",
            projected_returns={"base": 12.0, "bull": 16.0, "bear": 6.0},
            rationale="Index-heavy strategy",
            risks=["Market risk"],
            disclaimer="Research only",
        )
        mock_plan_result = MagicMock()
        mock_plan_result.output = fake_plan

        with patch("subprime.advisor.planner.create_advisor") as mock_ca:
            mock_agent2 = AsyncMock()
            mock_agent2.run = AsyncMock(return_value=mock_plan_result)
            mock_ca.return_value = mock_agent2

            plan = await generate_plan(profile, strategy=strategy)

        assert "UTI Nifty 50" in plan.allocations[0].fund.name
        plan_display = format_plan_summary(plan)
        assert "UTI Nifty 50" in plan_display

    def test_gather_profile_bulk_bypass(self):
        """gather_profile with existing_profile should bypass conversation."""
        import asyncio
        from subprime.advisor import gather_profile
        from subprime.evaluation import get_persona

        profile = get_persona("P01")

        async def should_not_be_called(msg: str) -> str:
            raise AssertionError("Should not be called")

        result = asyncio.run(
            gather_profile(send_message=should_not_be_called, existing_profile=profile)
        )
        assert result.id == "P01"
```

Add needed imports at top of `tests/test_integration.py` (merge with existing):
```python
from subprime.core.models import (
    ...,  # existing imports
    StrategyOutline,
)
```

- [ ] **Step 2: Run integration tests**

```bash
uv run pytest tests/test_integration.py -v
```

Expected: All tests PASS (new + existing).

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest -q
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add M1 integration tests for three-phase advisor flow"
```

---

### Task 8: Push

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests PASS.

- [ ] **Step 2: Push**

```bash
git push origin main
```
