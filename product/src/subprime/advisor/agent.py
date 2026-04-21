"""Advisor agent factory — assembles system prompt, registers tools."""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, PromptedOutput

from subprime.core.config import (
    DEFAULT_MODEL,
    build_model,
    build_model_settings,
    is_anthropic,
    is_vllm,
    tool_calls_reliable,
)


from subprime.core.models import InvestmentPlan, StrategyOutline
from subprime.data.tools import get_fund_details, search_funds_universe

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _output_for(model_id: str, schema_type):
    """Return the right output_type for this model's capabilities.

    Reliable tool-calling providers (anthropic / google / openai / groq /
    together Qwen3) get the raw pydantic model — pydantic-ai picks tool
    output and parses from the tool_call envelope. Everything else
    (workers-ai OpenAI-compat, unknown providers) gets PromptedOutput so
    the model emits JSON in text, which we parse client-side and avoid
    the compat layer's type-mangling entirely.
    """
    if tool_calls_reliable(model_id):
        return schema_type
    return PromptedOutput(schema_type)


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
    universe_context: str | None = None,
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
        universe_context: Optional markdown text describing the curated fund
            universe. When provided, it's appended to the system prompt so the
            agent knows which funds are available before making any tool calls.
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
    if universe_context:
        parts.append(universe_context)

    system_prompt = "\n\n---\n\n".join(parts)

    settings = build_model_settings(model, cache=True)
    tools_list = [search_funds_universe, get_fund_details]
    if is_anthropic(model):
        settings["anthropic_cache_tool_definitions"] = "1h"
    elif is_vllm(model):
        # Self-hosted small open-weight models loop on tool calls. The universe
        # is already in the system prompt, so tools only add a live-verify hop
        # we can't afford on a small advisor.
        tools_list = []

    return Agent(
        build_model(model, role="advisor"),
        system_prompt=system_prompt,
        output_type=_output_for(model, InvestmentPlan),
        tools=tools_list,
        retries=3,
        defer_model_check=True,
        model_settings=settings,
    )


def create_thinking_advisor(
    prompt_hooks: dict[str, str] | None = None,
    universe_context: str | None = None,
    model: str = DEFAULT_MODEL,
) -> Agent:
    """Create a thinking advisor that outputs free-form text (turn 1 of 2).

    Extended thinking is incompatible with constrained JSON output on large
    schemas.  This agent reasons deeply about the investor's needs and produces
    a detailed prose plan.  Follow up with :func:`create_plan_structurer` to
    convert the prose into an :class:`InvestmentPlan`.
    """
    base = load_prompt("base")
    planning = load_prompt("planning")

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
    if universe_context:
        parts.append(universe_context)

    system_prompt = "\n\n---\n\n".join(parts)

    settings = build_model_settings(model, cache=True, thinking=True)
    if is_anthropic(model):
        settings["anthropic_cache_tool_definitions"] = "1h"

    return Agent(
        build_model(model, role="advisor"),
        system_prompt=system_prompt,
        output_type=str,
        tools=[search_funds_universe, get_fund_details],
        retries=3,
        defer_model_check=True,
        model_settings=settings,
    )


def create_plan_structurer(
    model: str = DEFAULT_MODEL,
) -> Agent:
    """Create an agent that converts prose plan text into structured JSON (turn 2 of 2)."""
    return Agent(
        build_model(model, role="advisor"),
        system_prompt=(
            "You are a structured-data extraction agent. "
            "Given a detailed investment plan in prose, extract it into the "
            "required JSON schema exactly. Preserve all fund names, AMFI codes, "
            "allocations, percentages, and rationale from the source text. "
            "Do not add, remove, or modify any recommendations."
        ),
        output_type=_output_for(model, InvestmentPlan),
        tools=[],
        retries=3,
        defer_model_check=True,
    )


def create_plan_reviewer(
    model: str = DEFAULT_MODEL,
) -> Agent:
    """Create a senior-advisor plan reviewer agent.

    Takes a draft InvestmentPlan produced by a junior advisor and returns a
    refined version — same fund selections and approach, but with tighter
    rationale, corrected projections, complete risk disclosures, and
    actionable rebalancing guidelines.

    Args:
        model: The LLM model identifier (use a stronger model than the drafter).

    Returns:
        A PydanticAI Agent configured to output a refined InvestmentPlan.
    """
    review = load_prompt("review")

    return Agent(
        build_model(model, role="advisor"),
        system_prompt=review,
        output_type=_output_for(model, InvestmentPlan),
        tools=[],         # no tool calls — reviewer works from the draft text
        retries=2,
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
        build_model(model, role="advisor"),
        system_prompt=system_prompt,
        output_type=_output_for(model, StrategyOutline),
        tools=[],
        retries=2,
        defer_model_check=True,
    )
