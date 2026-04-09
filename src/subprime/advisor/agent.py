"""Advisor agent factory — assembles system prompt, registers tools."""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent

from subprime.core.config import DEFAULT_MODEL
from subprime.core.models import InvestmentPlan, StrategyOutline
from subprime.data.tools import compare_funds, get_fund_performance, search_funds

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory.

    Args:
        name: Prompt filename without extension (e.g. "base", "planning").

    Returns:
        The prompt text with leading/trailing whitespace stripped.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text().strip()


def create_advisor(
    prompt_hooks: dict[str, str] | None = None,
    model: str = DEFAULT_MODEL,
) -> Agent:
    """Create a financial advisor agent.

    Args:
        prompt_hooks: Optional dict of hook_name -> content to inject.
            e.g. {"philosophy": "Always prefer index funds."}
            If a key is provided, its VALUE (the actual text content, not a
            file path) replaces the corresponding hook file's content in the
            system prompt. If no hook or empty string, the philosophy section
            is omitted entirely.
        model: The LLM model identifier.

    Returns:
        A PydanticAI Agent configured with tools and prompts.
    """
    base = load_prompt("base")
    planning = load_prompt("planning")

    # Load hook content — either from the override or from the default file
    philosophy = ""
    if prompt_hooks and "philosophy" in prompt_hooks:
        philosophy = prompt_hooks["philosophy"]
    else:
        hook_path = _PROMPTS_DIR / "hooks" / "philosophy.md"
        if hook_path.exists():
            philosophy = hook_path.read_text().strip()

    parts = [base, planning]
    if philosophy:
        parts.append(f"## Investment Philosophy\n\n{philosophy}")

    system_prompt = "\n\n---\n\n".join(parts)

    return Agent(
        model,
        system_prompt=system_prompt,
        output_type=InvestmentPlan,
        tools=[search_funds, get_fund_performance, compare_funds],
        retries=3,
        defer_model_check=True,
    )


def create_strategy_advisor(
    prompt_hooks: dict[str, str] | None = None,
    model: str = DEFAULT_MODEL,
) -> Agent:
    """Create a strategy-only advisor (no fund lookups, no tools).

    Used in Phase 2 — proposes high-level asset allocation
    before selecting specific funds.
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
