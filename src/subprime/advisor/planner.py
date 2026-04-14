"""Plan generation — strategy outlines and detailed investment plans."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pydantic_ai.settings import ModelSettings

from subprime.advisor.agent import create_advisor, create_plan_reviewer, create_strategy_advisor
from subprime.core.config import DB_PATH, DEFAULT_MODEL
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
) -> StrategyOutline:
    """Generate or revise a high-level investment strategy."""
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
    return result.output


async def _generate_single_plan(
    profile: InvestorProfile,
    strategy: StrategyOutline | None,
    prompt_hooks: dict[str, str] | None,
    universe_ctx: str | None,
    perspective_prompt: str | None,
    perspective_name: str,
    model: str,
    temperature: float | None = None,
) -> InvestmentPlan:
    """Generate a single plan, optionally with a perspective prompt."""
    # Merge perspective prompt into hooks
    hooks = dict(prompt_hooks or {})
    if perspective_prompt:
        existing_philosophy = hooks.get("philosophy", "")
        if existing_philosophy:
            hooks["philosophy"] = existing_philosophy + "\n\n" + perspective_prompt
        else:
            hooks["philosophy"] = perspective_prompt

    agent = create_advisor(
        prompt_hooks=hooks,
        universe_context=universe_ctx,
        model=model,
    )

    parts = [
        f"Create a detailed mutual fund investment plan for this investor:\n\n"
        f"{profile.model_dump_json(indent=2)}"
    ]
    if strategy:
        parts.append(
            f"\nThe investor has approved this strategy direction:\n\n"
            f"{strategy.model_dump_json(indent=2)}\n\n"
            f"Select specific mutual fund schemes that implement this strategy. "
            f"Prefer funds from the curated universe above when possible."
        )

    model_settings = ModelSettings(temperature=temperature) if temperature else None
    result = await agent.run("\n".join(parts), model_settings=model_settings)
    plan = result.output
    plan.perspective = perspective_name
    return plan


async def refine_plan(
    draft: InvestmentPlan,
    profile: InvestorProfile,
    model: str = DEFAULT_MODEL,
) -> InvestmentPlan:
    """Review and refine a draft plan as a senior advisor reviewing associate work.

    The reviewer checks goal coverage, rationale quality, internal consistency,
    risk appropriateness, projected returns, and actionability of guidelines —
    then returns a polished final plan without changing the core fund selections.

    Args:
        draft: The draft InvestmentPlan produced by the junior advisor.
        profile: The investor's profile for context.
        model: The LLM model for the reviewer (should be stronger than drafter).

    Returns:
        A refined InvestmentPlan.
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
    return refined


async def generate_plan(
    profile: InvestorProfile,
    strategy: StrategyOutline | None = None,
    prompt_hooks: dict[str, str] | None = None,
    include_universe: bool = True,
    mode: str = "basic",
    n_perspectives: int = 3,
    model: str = DEFAULT_MODEL,
    refine_model: str | None = None,
) -> InvestmentPlan:
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
    """
    universe_ctx = _load_universe_context() if include_universe else None

    if mode == "premium":
        from subprime.advisor.evaluator import evaluate_plans
        from subprime.advisor.perspectives import get_default_perspectives

        perspectives = get_default_perspectives(n_perspectives)
        logger.info("Premium mode: generating %d perspectives", len(perspectives))

        # Generate plans in parallel
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
        plans = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out failures
        valid_plans = [p for p in plans if isinstance(p, InvestmentPlan)]
        if not valid_plans:
            logger.error("All premium variants failed, falling back to basic mode")
            return await _generate_single_plan(
                profile, strategy, prompt_hooks, universe_ctx,
                None, "basic_fallback", model,
            )

        if len(valid_plans) == 1:
            best = valid_plans[0]
        else:
            # Evaluate and pick best
            evaluation = await evaluate_plans(valid_plans, profile, model)
            best = valid_plans[evaluation.best_index]
            logger.info(
                "Premium evaluation: picked '%s' — %s",
                best.perspective,
                evaluation.reasoning[:100],
            )

        if refine_model:
            logger.info("Refining premium plan with %s", refine_model)
            best = await refine_plan(best, profile, model=refine_model)
        return best

    # basic mode
    plan = await _generate_single_plan(
        profile, strategy, prompt_hooks, universe_ctx,
        None, "basic", model,
    )
    if refine_model:
        logger.info("Refining basic plan with %s", refine_model)
        plan = await refine_plan(plan, profile, model=refine_model)
    return plan
