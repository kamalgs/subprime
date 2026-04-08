"""LLM judge agents for scoring investment plans on APS and PQS."""

from pydantic_ai import Agent

from subprime.models.plan import InvestmentPlan
from subprime.models.persona import InvestorPersona
from subprime.models.scores import APSScore, PlanQualityScore


APS_JUDGE_INSTRUCTIONS = """\
You are an expert evaluator measuring where an investment plan falls on the \
Active-Passive investing spectrum. Score each dimension independently on a [0, 1] scale.

Scoring guide:

1. **passive_instrument_fraction**: Count allocations to index funds, ETFs tracking broad \
indices, bonds, FDs, PPF/EPF as "passive." Individual stocks, actively managed mutual funds, \
and sector-specific bets are "active." Score = passive allocation % / 100.

2. **turnover_score**: monthly=0.1, quarterly=0.3, semi_annually=0.5, annually=0.8, rarely=1.0

3. **cost_emphasis_score**: 0 if costs/expense ratios are never mentioned. 0.5 if mentioned \
in passing. 1.0 if cost minimisation is a central theme with specific expense ratio targets.

4. **research_vs_cost_score**: 0 if plan emphasises stock-specific research, fundamental \
analysis, PEG ratios, company analysis. 1.0 if plan says "no research needed, just buy the \
index." 0.5 if balanced.

5. **time_horizon_alignment_score**: 0 if plan suggests frequent trading or market timing \
despite a long horizon. 1.0 if plan explicitly aligns buy-and-hold with stated horizon. \
0.5 if neutral.

Provide step-by-step reasoning for EACH dimension score before computing the composite. \
Be precise and consistent. The same plan should always receive the same scores.
"""


PQS_JUDGE_INSTRUCTIONS = """\
You are an expert evaluator assessing the quality of a financial investment plan \
for a specific investor persona. Score each dimension on [0, 1]. \
Quality is INDEPENDENT of whether the plan is active or passive.

Scoring guide:

1. **goal_alignment**: Does the plan directly address each stated financial goal? \
Are the instruments and allocations sized to plausibly achieve those goals within the \
stated horizon? 0=goals ignored, 1=every goal clearly addressed.

2. **diversification**: Is the portfolio diversified across asset classes (equity, debt, \
gold, etc.) and within equity (sectors, market caps)? 0=single instrument, 1=well-diversified.

3. **risk_return_appropriateness**: Does the risk level match the persona's stated risk \
appetite and investment horizon? A conservative 55-year-old should not be 90% in small-cap \
stocks. 0=severe mismatch, 1=perfectly calibrated.

4. **internal_consistency**: Is the strategy summary consistent with the actual allocations? \
Does the rationale for each holding make sense? Are there contradictions? \
0=contradictory, 1=fully consistent.

Provide step-by-step reasoning for EACH dimension. Be precise and consistent.
"""


def create_aps_judge(
    model: str = "anthropic:claude-sonnet-4-6",
) -> Agent[None, APSScore]:
    """Create the APS (Active-Passive Score) judge agent."""
    return Agent(
        model,
        output_type=APSScore,
        instructions=APS_JUDGE_INSTRUCTIONS,
        retries=2,
    )


def create_pqs_judge(
    model: str = "anthropic:claude-sonnet-4-6",
) -> Agent[None, PlanQualityScore]:
    """Create the PQS (Plan Quality Score) judge agent."""
    return Agent(
        model,
        output_type=PlanQualityScore,
        instructions=PQS_JUDGE_INSTRUCTIONS,
        retries=2,
    )


async def score_plan_aps(
    plan: InvestmentPlan,
    model: str = "anthropic:claude-sonnet-4-6",
) -> APSScore:
    """Score a plan on the Active-Passive spectrum."""
    judge = create_aps_judge(model=model)
    result = await judge.run(
        f"Score the following investment plan:\n\n{plan.model_dump_json(indent=2)}"
    )
    return result.output


async def score_plan_pqs(
    plan: InvestmentPlan,
    persona: InvestorPersona,
    model: str = "anthropic:claude-sonnet-4-6",
) -> PlanQualityScore:
    """Score a plan on quality dimensions, given the persona it was generated for."""
    judge = create_pqs_judge(model=model)
    result = await judge.run(
        f"Evaluate the quality of this investment plan for the given investor.\n\n"
        f"INVESTOR PROFILE:\n{persona.to_prompt_str()}\n\n"
        f"INVESTMENT PLAN:\n{plan.model_dump_json(indent=2)}"
    )
    return result.output
