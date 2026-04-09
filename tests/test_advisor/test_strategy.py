"""Tests for strategy advisor factory — verifies wiring, not LLM quality.

Only the LLM is mocked. Everything else (prompt loading, agent creation)
runs for real.
"""

from __future__ import annotations

from subprime.advisor.agent import create_strategy_advisor, load_prompt


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------


def test_load_prompt_strategy():
    prompt = load_prompt("strategy")
    assert "asset allocation" in prompt.lower()
    assert "equity" in prompt.lower()


def test_load_prompt_profile():
    prompt = load_prompt("profile")
    assert "risk appetite" in prompt.lower()
    assert "INR" in prompt


# ---------------------------------------------------------------------------
# Agent creation
# ---------------------------------------------------------------------------


def test_create_strategy_advisor_default():
    agent = create_strategy_advisor()
    assert agent is not None


def test_create_strategy_advisor_has_no_tools():
    agent = create_strategy_advisor()
    assert len(agent._function_toolset.tools) == 0


def test_create_strategy_advisor_with_hook():
    agent = create_strategy_advisor(
        prompt_hooks={"philosophy": "Always prefer index funds."}
    )
    assert agent is not None


def test_create_strategy_advisor_hook_in_system_prompt():
    hook_text = "TEST_STRATEGY_HOOK_MARKER: prefer active stock picking"
    agent = create_strategy_advisor(prompt_hooks={"philosophy": hook_text})
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "TEST_STRATEGY_HOOK_MARKER" in combined


def test_create_strategy_advisor_baseline_no_philosophy():
    """Baseline (no hook) system prompt must NOT contain a philosophy section."""
    agent = create_strategy_advisor()
    combined = " ".join(str(s) for s in agent._system_prompts)
    assert "Investment Philosophy" not in combined
