"""Plan generation — strategy outlines and detailed investment plans."""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from subprime.advisor.agent import create_advisor, create_strategy_advisor
from subprime.core.config import DB_PATH, DEFAULT_MODEL
from subprime.core.models import InvestmentPlan, InvestorProfile, StrategyOutline

logger = logging.getLogger(__name__)


def _load_universe_context(db_path: Path | None = None) -> str | None:
    """Load the curated fund universe as markdown text from DuckDB.

    Returns None if the database doesn't exist or is empty — the advisor
    will then work without the universe (falling back to live tool calls).
    """
    # Look up DB_PATH at call time so tests can monkeypatch the module attribute.
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


class PlanRanking(BaseModel):
    """Result of comparing multiple plan variants."""

    best_index: int
    reasoning: str


async def _pick_best_plan(
    plans: list[InvestmentPlan], profile: InvestorProfile, model: str
) -> InvestmentPlan:
    """Pick the best plan from variants using a quick LLM evaluation."""
    scorer = Agent(
        model,
        system_prompt=(
            "You are evaluating investment plans. Pick the best one based on: "
            "goal alignment, diversification across fund houses, cost efficiency "
            "(expense ratios), and appropriateness for the investor's risk profile."
        ),
        output_type=PlanRanking,
        defer_model_check=True,
    )

    plans_text = "\n\n---\n\n".join(
        f"Plan {i + 1}:\n{p.model_dump_json(indent=2)}" for i, p in enumerate(plans)
    )
    prompt = (
        f"Investor:\n{profile.model_dump_json(indent=2)}\n\n"
        f"Plans:\n{plans_text}\n\n"
        f"Which plan is best? Return the index (0-based)."
    )
    result = await scorer.run(prompt)
    idx = max(0, min(result.output.best_index, len(plans) - 1))
    return plans[idx]


async def generate_plan(
    profile: InvestorProfile,
    strategy: StrategyOutline | None = None,
    prompt_hooks: dict[str, str] | None = None,
    include_universe: bool = True,
    mode: str = "basic",
    model: str = DEFAULT_MODEL,
) -> InvestmentPlan:
    """Generate a detailed investment plan.

    Args:
        profile: Complete investor profile.
        strategy: Optional approved strategy to guide fund selection.
        prompt_hooks: Optional philosophy injection for experiments.
        include_universe: If True (default), load the curated fund universe
            from DuckDB and inject into the agent's system prompt.
        mode: Plan generation mode — ``"basic"`` (single plan) or
            ``"premium"`` (generate 3 variants, score and pick the best).
        model: LLM model identifier.
    """
    universe_ctx = _load_universe_context() if include_universe else None

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

    prompt = "\n".join(parts)

    if mode == "premium":
        logger.info("Premium mode: generating 3 plan variants")
        variants: list[InvestmentPlan] = []
        for i in range(3):
            agent = create_advisor(
                prompt_hooks=prompt_hooks,
                universe_context=universe_ctx,
                model=model,
            )
            result = await agent.run(
                prompt, model_settings=ModelSettings(temperature=0.9)
            )
            variants.append(result.output)
            logger.info("Generated variant %d/3", i + 1)

        best = await _pick_best_plan(variants, profile, model)
        return best

    # basic mode — single generation
    agent = create_advisor(
        prompt_hooks=prompt_hooks,
        universe_context=universe_ctx,
        model=model,
    )
    result = await agent.run(prompt)
    return result.output
