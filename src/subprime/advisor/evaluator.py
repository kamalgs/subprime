"""Plan evaluator — compares multiple plan variants and picks the best.

Used by premium mode after generating plans from different perspectives.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel
from pydantic_ai import Agent

from subprime.core.config import DEFAULT_MODEL
from subprime.core.models import InvestmentPlan, InvestorProfile

logger = logging.getLogger(__name__)


class PlanEvaluation(BaseModel):
    """Evaluation result for a set of plan variants."""
    best_index: int
    rankings: list[int] = []  # ordered indices, best first
    reasoning: str
    strengths: dict[str, str] = {}  # perspective_name -> key strength
    weaknesses: dict[str, str] = {}  # perspective_name -> key weakness


async def evaluate_plans(
    plans: list[InvestmentPlan],
    profile: InvestorProfile,
    model: str = DEFAULT_MODEL,
) -> PlanEvaluation:
    """Compare plan variants and pick the best for the investor.

    The evaluator considers:
    - Goal alignment: does the plan address this specific person's goals?
    - Diversification: fund house spread, asset class coverage
    - Cost efficiency: expense ratios, direct plans
    - Practicality: can the investor actually follow this plan?
    - Risk fit: does the risk level match their stated comfort?
    """
    evaluator = Agent(
        model,
        system_prompt=(
            "You are an expert evaluator comparing investment plans for an Indian investor. "
            "Each plan was created from a different advisory perspective. "
            "Pick the best one for THIS specific investor based on:\n"
            "1. Goal alignment — does it address their specific goals and timeline?\n"
            "2. Diversification — spread across fund houses and asset classes\n"
            "3. Cost efficiency — lower fees compound into bigger returns\n"
            "4. Practicality — can a regular person actually follow this plan?\n"
            "5. Risk fit — matches their stated risk comfort level\n\n"
            "For each plan, note its key strength and weakness. "
            "Return the index (0-based) of the best plan and your reasoning in plain language."
        ),
        output_type=PlanEvaluation,
        retries=2,
        defer_model_check=True,
    )

    plans_text = "\n\n===\n\n".join(
        f"Plan {i} — Perspective: {p.perspective or 'unknown'}\n"
        f"Allocations: {len(p.allocations)} funds\n"
        f"Rationale: {p.rationale}\n"
        f"SIP Step-Up: {p.sip_step_up.description if p.sip_step_up else 'None'}\n"
        f"Allocation Phases: {len(p.allocation_schedule)}\n"
        f"Projected Returns: {p.projected_returns}\n"
        f"Risks: {', '.join(p.risks[:3])}"
        for i, p in enumerate(plans)
    )

    prompt = (
        f"## Investor Profile\n\n{profile.model_dump_json(indent=2)}\n\n"
        f"## Plans to Compare\n\n{plans_text}"
    )

    result = await evaluator.run(prompt)
    evaluation = result.output
    # Clamp index
    evaluation.best_index = max(0, min(evaluation.best_index, len(plans) - 1))
    return evaluation
