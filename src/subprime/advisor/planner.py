"""Plan generation — strategy outlines and detailed investment plans."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

from subprime.advisor.agent import create_advisor, create_plan_reviewer, create_strategy_advisor
from subprime.core.config import DB_PATH, DEFAULT_MODEL, is_anthropic, supports_thinking
from subprime.core.models import InvestmentPlan, InvestorProfile, StrategyOutline

logger = logging.getLogger(__name__)


def _load_universe_context(db_path: Path | None = None) -> str | None:
    """Load the curated fund universe as markdown text from DuckDB."""
    if db_path is None:
        from subprime.advisor import planner as _self
        db_path = _self.DB_PATH
    if not db_path.exists():
        return None
    try:
        import duckdb
        from subprime.data.universe import render_universe_context
        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            return render_universe_context(conn)
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to load fund universe from %s", db_path, exc_info=True)
        return None


async def generate_strategy(
    profile: InvestorProfile,
    feedback: str | None = None,
    current_strategy: StrategyOutline | None = None,
    prompt_hooks: dict[str, str] | None = None,
    model: str = DEFAULT_MODEL,
) -> tuple[StrategyOutline, RunUsage]:
    """Generate or revise a high-level investment strategy.

    Returns:
        (StrategyOutline, RunUsage) — strategy and token usage.
    """
    agent = create_strategy_advisor(prompt_hooks=prompt_hooks, model=model)
    parts = [f"Investor profile:\n\n{profile.model_dump_json(indent=2)}"]
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
    return result.output, result.usage()


async def _generate_single_plan(
    profile: InvestorProfile,
    strategy: StrategyOutline | None,
    prompt_hooks: dict[str, str] | None,
    universe_ctx: str | None,
    perspective_prompt: str | None,
    perspective_name: str,
    model: str,
    temperature: float | None = None,
    thinking: bool = False,
) -> tuple[InvestmentPlan, RunUsage]:
    """Generate a single plan, optionally with a perspective prompt.

    When *thinking* is True, uses a two-turn flow: (1) thinking advisor
    produces a detailed prose plan, (2) structurer extracts it into
    :class:`InvestmentPlan` JSON.

    Returns:
        (InvestmentPlan, RunUsage) — plan and combined token usage.
    """
    from pydantic_ai.usage import RunUsage as _RU

    # Merge perspective prompt into hooks
    hooks = dict(prompt_hooks or {})
    if perspective_prompt:
        existing_philosophy = hooks.get("philosophy", "")
        if existing_philosophy:
            hooks["philosophy"] = existing_philosophy + "\n\n" + perspective_prompt
        else:
            hooks["philosophy"] = perspective_prompt

    user_parts = [
        f"Create a detailed mutual fund investment plan for this investor:\n\n"
        f"{profile.model_dump_json(indent=2)}"
    ]
    if strategy:
        user_parts.append(
            f"\nThe investor has approved this strategy direction:\n\n"
            f"{strategy.model_dump_json(indent=2)}\n\n"
            f"Select specific mutual fund schemes that implement this strategy. "
            f"Prefer funds from the curated universe above when possible."
        )
    user_prompt = "\n".join(user_parts)

    if thinking and supports_thinking(model) and is_anthropic(model):
        from subprime.advisor.agent import create_plan_structurer, create_thinking_advisor

        advisor = create_thinking_advisor(
            prompt_hooks=hooks,
            universe_context=universe_ctx,
            model=model,
        )
        model_settings = ModelSettings(temperature=temperature) if temperature else None
        think_result = await advisor.run(user_prompt, model_settings=model_settings)
        prose_plan = think_result.output

        structurer = create_plan_structurer(model=model)
        struct_result = await structurer.run(
            f"Extract this investment plan into the required JSON structure:\n\n{prose_plan}"
        )
        plan = struct_result.output
        plan.perspective = perspective_name

        combined = think_result.usage()
        combined.incr(struct_result.usage())
        return plan, combined
    else:
        agent = create_advisor(
            prompt_hooks=hooks,
            universe_context=universe_ctx,
            model=model,
        )
        model_settings = ModelSettings(temperature=temperature) if temperature else None
        result = await agent.run(user_prompt, model_settings=model_settings)
        plan = result.output
        plan.perspective = perspective_name
        return plan, result.usage()


async def refine_plan(
    draft: InvestmentPlan,
    profile: InvestorProfile,
    model: str = DEFAULT_MODEL,
) -> tuple[InvestmentPlan, RunUsage]:
    """Review and refine a draft plan as a senior advisor reviewing associate work.

    The reviewer checks goal coverage, rationale quality, internal consistency,
    risk appropriateness, projected returns, and actionability of guidelines —
    then returns a polished final plan without changing the core fund selections.

    Args:
        draft: The draft InvestmentPlan produced by the junior advisor.
        profile: The investor's profile for context.
        model: The LLM model for the reviewer (should be stronger than drafter).

    Returns:
        (InvestmentPlan, RunUsage) — refined plan and token usage.
    """
    reviewer = create_plan_reviewer(model=model)
    prompt = (
        "Review and refine the following draft investment plan.\n\n"
        f"## Client Profile\n{profile.model_dump_json(indent=2)}\n\n"
        f"## Draft Plan (prepared by associate)\n{draft.model_dump_json(indent=2)}"
    )
    result = await reviewer.run(prompt)
    refined = result.output
    # Preserve the perspective tag from the draft
    refined.perspective = draft.perspective
    return refined, result.usage()


async def generate_plan(
    profile: InvestorProfile,
    strategy: StrategyOutline | None = None,
    prompt_hooks: dict[str, str] | None = None,
    include_universe: bool = True,
    mode: str = "basic",
    n_perspectives: int = 3,
    model: str = DEFAULT_MODEL,
    refine_model: str | None = None,
    thinking: bool = False,
) -> tuple[InvestmentPlan, RunUsage]:
    """Generate a detailed investment plan.

    Args:
        profile: Complete investor profile.
        strategy: Optional approved strategy to guide fund selection.
        prompt_hooks: Optional philosophy injection for experiments.
        include_universe: Load curated fund universe from DuckDB.
        mode: "basic" (single plan) or "premium" (multi-perspective comparison).
        n_perspectives: Number of perspectives for premium mode (3 or 5).
        model: LLM model identifier for the advisor (drafter).
        refine_model: If set, run a senior-advisor review pass on the draft
            using this model before returning. Improves rationale quality and
            completeness without changing fund selections.

    Returns:
        (InvestmentPlan, RunUsage) — plan and aggregated token usage.
    """
    universe_ctx = _load_universe_context() if include_universe else None
    total_usage = RunUsage()

    if mode == "premium":
        from subprime.advisor.evaluator import evaluate_plans
        from subprime.advisor.perspectives import get_default_perspectives

        perspectives = get_default_perspectives(n_perspectives)
        logger.info("Premium mode: generating %d perspectives", len(perspectives))

        tasks = [
            _generate_single_plan(
                profile=profile,
                strategy=strategy,
                prompt_hooks=prompt_hooks,
                universe_ctx=universe_ctx,
                perspective_prompt=p.prompt,
                perspective_name=p.name,
                model=model,
                temperature=0.8,
            )
            for p in perspectives
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid: list[tuple[InvestmentPlan, RunUsage]] = [
            r for r in results if isinstance(r, tuple)
        ]
        if not valid:
            logger.error("All premium variants failed, falling back to basic mode")
            plan, usage = await _generate_single_plan(
                profile, strategy, prompt_hooks, universe_ctx,
                None, "basic_fallback", model,
            )
            total_usage.incr(usage)
            return plan, total_usage

        valid_plans = [p for p, _ in valid]
        for _, u in valid:
            total_usage.incr(u)

        if len(valid_plans) == 1:
            best = valid_plans[0]
        else:
            evaluation, eval_usage = await evaluate_plans(valid_plans, profile, model)
            total_usage.incr(eval_usage)
            best = valid_plans[evaluation.best_index]
            logger.info(
                "Premium evaluation: picked '%s' — %s",
                best.perspective,
                evaluation.reasoning[:100],
            )

        if refine_model:
            logger.info("Refining premium plan with %s", refine_model)
            best, refine_usage = await refine_plan(best, profile, model=refine_model)
            total_usage.incr(refine_usage)
        return best, total_usage

    # basic mode
    plan, usage = await _generate_single_plan(
        profile, strategy, prompt_hooks, universe_ctx,
        None, "basic", model, thinking=thinking,
    )
    total_usage.incr(usage)
    if refine_model:
        logger.info("Refining basic plan with %s", refine_model)
        plan, refine_usage = await refine_plan(plan, profile, model=refine_model)
        total_usage.incr(refine_usage)
    return plan, total_usage
