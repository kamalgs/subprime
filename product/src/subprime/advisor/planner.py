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


# Category-typical CAGRs (%) — used to compute fallback projected returns
# when the LLM leaves plan.projected_returns empty or zero.
_CATEGORY_CAGR = {
    "large cap": 11.0,
    "mid cap": 13.0,
    "small cap": 15.0,
    "flexi cap": 12.0,
    "multi cap": 12.0,
    "elss": 12.0,
    "index": 11.0,
    "nifty": 11.0,
    "sensex": 11.0,
    "hybrid": 9.5,
    "balanced": 9.5,
    "arbitrage": 6.5,
    "debt": 7.0,
    "liquid": 6.0,
    "overnight": 5.5,
    "gilt": 7.5,
    "corporate bond": 7.5,
    "short duration": 7.0,
    "gold": 9.0,
    "international": 10.0,
}

_RISK_DEFAULTS = {
    "aggressive": {"bear": 8.0, "base": 12.0, "bull": 16.0},
    "moderate": {"bear": 6.0, "base": 10.0, "bull": 14.0},
    "conservative": {"bear": 5.0, "base": 8.0, "bull": 11.0},
}


def _category_cagr(category: str, sub_category: str = "") -> float | None:
    """Look up category-typical CAGR by matching on category/sub_category substrings."""
    haystack = f"{category} {sub_category}".lower()
    for key, cagr in _CATEGORY_CAGR.items():
        if key in haystack:
            return cagr
    return None


def fill_projected_returns_fallback(plan: InvestmentPlan, profile: InvestorProfile) -> None:
    """Populate plan.projected_returns if the LLM left it empty or zero.

    Strategy:
      1. If existing values already look valid (base > 0), leave them alone.
      2. Otherwise compute base CAGR as allocation-weighted average of
         category-typical CAGRs; set bull = base + 4, bear = base - 4.
      3. If allocation categories can't be matched, fall back to risk-appetite
         defaults so the returns table always renders.
    """
    pr = plan.projected_returns or {}
    base = pr.get("base", 0.0) or 0.0
    if base > 0:
        # Still fill in missing bull/bear so downstream rendering is safe
        if not pr.get("bull"):
            plan.projected_returns["bull"] = round(base + 4.0, 2)
        if not pr.get("bear"):
            plan.projected_returns["bear"] = round(max(base - 4.0, 1.0), 2)
        return

    weighted_sum = 0.0
    matched_pct = 0.0
    for a in plan.allocations:
        cagr = _category_cagr(a.fund.category, a.fund.sub_category)
        if cagr is not None:
            weighted_sum += cagr * a.allocation_pct
            matched_pct += a.allocation_pct

    if matched_pct >= 50:
        base_cagr = round(weighted_sum / matched_pct, 2)
    else:
        base_cagr = _RISK_DEFAULTS.get(profile.risk_appetite, _RISK_DEFAULTS["moderate"])["base"]

    plan.projected_returns = {
        "bear": round(max(base_cagr - 4.0, 1.0), 2),
        "base": base_cagr,
        "bull": round(base_cagr + 4.0, 2),
    }
    logger.info(
        "Filled fallback projected_returns for %s: %s (matched_pct=%.1f)",
        profile.id,
        plan.projected_returns,
        matched_pct,
    )


# Universe markdown is cached on disk next to the DuckDB file after the
# first render, so subsequent processes / requests skip the DuckDB round-trip.
# The in-process cache is additionally held so hot requests don't even re-read
# the file. `subprime data refresh` invalidates the cache by deleting the file.
_UNIVERSE_CACHE_TEXT: str | None = None


def _universe_cache_path(db_path: Path) -> Path:
    return db_path.parent / "universe_context.md"


def _render_universe_from_db(db_path: Path, max_per_category: int | None = None) -> str | None:
    """Open DuckDB read-only and render the universe markdown (slow path).

    ``max_per_category`` caps rows per category for the slim variant.
    """
    try:
        import duckdb
        from subprime.data.universe import render_universe_context

        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            return render_universe_context(conn, max_per_category=max_per_category)
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to render fund universe from %s", db_path, exc_info=True)
        return None


_UNIVERSE_SLIM_CACHE: str | None = None
_SLIM_PER_CATEGORY = 5


def warm_universe_cache(db_path: Path | None = None) -> bool:
    """Build the on-disk universe cache if it's missing or stale.

    Called once at web-app startup (via lifespan) so the first request
    doesn't pay the DuckDB + markdown rendering cost.
    Returns True if the cache was (re)built, False if already warm or DB missing.
    """
    global _UNIVERSE_CACHE_TEXT
    if db_path is None:
        db_path = DB_PATH
    if not db_path.exists():
        return False

    cache_path = _universe_cache_path(db_path)
    try:
        # Rebuild if cache is missing or older than the DB file.
        if not cache_path.exists() or cache_path.stat().st_mtime < db_path.stat().st_mtime:
            text = _render_universe_from_db(db_path)
            if text is None:
                return False
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(text)
            _UNIVERSE_CACHE_TEXT = text
            logger.info(
                "Universe cache warmed: %d chars → %s",
                len(text),
                cache_path,
            )
            return True

        _UNIVERSE_CACHE_TEXT = cache_path.read_text()
        logger.info(
            "Universe cache hit: %d chars from %s",
            len(_UNIVERSE_CACHE_TEXT),
            cache_path,
        )
        return False
    except Exception:
        logger.exception("warm_universe_cache failed")
        return False


def _load_universe_context(db_path: Path | None = None, slim: bool = False) -> str | None:
    """Return the fund universe markdown — from in-memory cache if present,
    else the on-disk cache file, else (last resort) render from DuckDB.

    When ``slim`` is True, returns a reduced version (``_SLIM_PER_CATEGORY``
    rows per category) cached separately in-process. Used for basic-tier
    plans to cut input tokens without touching the full-universe cache.
    """
    global _UNIVERSE_CACHE_TEXT, _UNIVERSE_SLIM_CACHE

    if slim and _UNIVERSE_SLIM_CACHE is not None:
        return _UNIVERSE_SLIM_CACHE
    if not slim and _UNIVERSE_CACHE_TEXT is not None:
        return _UNIVERSE_CACHE_TEXT

    if db_path is None:
        from subprime.advisor import planner as _self

        db_path = _self.DB_PATH
    if not db_path.exists():
        return None

    if slim:
        text = _render_universe_from_db(db_path, max_per_category=_SLIM_PER_CATEGORY)
        if text is not None:
            _UNIVERSE_SLIM_CACHE = text
        return text

    cache_path = _universe_cache_path(db_path)
    try:
        if cache_path.exists() and cache_path.stat().st_mtime >= db_path.stat().st_mtime:
            _UNIVERSE_CACHE_TEXT = cache_path.read_text()
            return _UNIVERSE_CACHE_TEXT
    except Exception:
        logger.warning("Failed reading universe cache %s", cache_path, exc_info=True)

    text = _render_universe_from_db(db_path)
    if text is not None:
        _UNIVERSE_CACHE_TEXT = text
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(text)
        except Exception:
            logger.warning("Could not write universe cache", exc_info=True)
    return text


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
    parts = [f"Investor profile:\n\n{_profile_to_prompt_json(profile, cache_safe=True)}"]
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


def _profile_to_prompt_json(profile: InvestorProfile, *, cache_safe: bool = False) -> str:
    """Serialise a profile for the LLM prompt.

    When *cache_safe*, replace identifying fields (name) with a stable
    placeholder so two users with the same archetype produce the same
    prompt byte-for-byte. The real name stays in the session for UI
    rendering; the advisor doesn't need it to plan.

    Intentionally narrow: only swaps the name. Everything else is
    semantically meaningful to the plan and should survive.
    """
    data = profile.model_dump(mode="json")
    if cache_safe:
        data["name"] = "Investor"
    import json

    return json.dumps(data, indent=2, sort_keys=True)


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

    # Merge perspective prompt into hooks
    hooks = dict(prompt_hooks or {})
    if perspective_prompt:
        existing_philosophy = hooks.get("philosophy", "")
        if existing_philosophy:
            hooks["philosophy"] = existing_philosophy + "\n\n" + perspective_prompt
        else:
            hooks["philosophy"] = perspective_prompt

    # For Basic-tier archetype users the name is the only varying field;
    # strip it so the cached prompt can be reused across users who pick the
    # same archetype without editing anything.
    profile_json = _profile_to_prompt_json(profile, cache_safe=True)
    user_parts = [
        f"Create a detailed mutual fund investment plan for this investor:\n\n{profile_json}"
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
        f"## Client Profile\n{_profile_to_prompt_json(profile, cache_safe=True)}\n\n"
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
    slim_universe: bool = False,
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
    universe_ctx = _load_universe_context(slim=slim_universe) if include_universe else None
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

        valid: list[tuple[InvestmentPlan, RunUsage]] = [r for r in results if isinstance(r, tuple)]
        if not valid:
            logger.error("All premium variants failed, falling back to basic mode")
            plan, usage = await _generate_single_plan(
                profile,
                strategy,
                prompt_hooks,
                universe_ctx,
                None,
                "basic_fallback",
                model,
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
        fill_projected_returns_fallback(best, profile)
        return best, total_usage

    # basic mode
    plan, usage = await _generate_single_plan(
        profile,
        strategy,
        prompt_hooks,
        universe_ctx,
        None,
        "basic",
        model,
        thinking=thinking,
    )
    total_usage.incr(usage)
    if refine_model:
        logger.info("Refining basic plan with %s", refine_model)
        plan, refine_usage = await refine_plan(plan, profile, model=refine_model)
        total_usage.incr(refine_usage)
    fill_projected_returns_fallback(plan, profile)
    return plan, total_usage
