"""Run a fine-tuned model against the 25-persona bank and score with APS+PQS.

Wraps the FT endpoint behind a PydanticAI Agent so PromptedOutput retries
handle JSON drift (matches advisor/agent.py methodology). Mirrors
experiments/runner.py output format so existing analysis works unchanged.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent, PromptedOutput

from subprime.core.config import DEFAULT_MODEL, build_model, build_model_settings
from subprime.core.models import (
    APSScore,
    ExperimentResult,
    InvestmentPlan,
    InvestorProfile,
    PlanQualityScore,
)
from subprime.evaluation.judges import score_aps, score_pqs
from subprime.evaluation.personas import load_personas
from subprime.finetuning.format import NEUTRAL_SYSTEM_PROMPT, render_profile_text
from subprime.finetuning.provider import EndpointInfo, FineTuneProvider


def build_ft_agent(endpoint: EndpointInfo) -> Agent:
    """Build a PydanticAI Agent that routes through a Together endpoint.

    The endpoint must already be STARTED. Uses the endpoint NAME (not the
    raw FT model name) since Together's chat.completions API routes by
    endpoint name. Output is constrained to InvestmentPlan via
    PromptedOutput, with retries on validation errors.
    """
    model_id = f"together:{endpoint.name}"
    pa_model = build_model(model_id)
    settings = build_model_settings(model_id, thinking=False)
    return Agent(
        pa_model,
        system_prompt=NEUTRAL_SYSTEM_PROMPT,
        output_type=PromptedOutput(InvestmentPlan),
        retries=3,
        model_settings=settings,
    )


class EvalRecord(BaseModel):
    persona_id: str
    output_model: str
    parsed: bool
    plan: InvestmentPlan | None = None
    aps: APSScore | None = None
    pqs: PlanQualityScore | None = None
    error: str | None = None


async def evaluate_persona(
    profile: InvestorProfile,
    *,
    agent: Agent,
    output_model: str,
    judge_model: str = DEFAULT_MODEL,
) -> EvalRecord:
    user_msg = render_profile_text(profile)
    try:
        result = await agent.run(user_msg)
        plan = result.output
    except Exception as e:
        return EvalRecord(
            persona_id=profile.id,
            output_model=output_model,
            parsed=False,
            error=f"{type(e).__name__}: {e}",
        )

    aps, _ = await score_aps(plan, profile, model=judge_model)
    pqs, _ = await score_pqs(plan, profile, model=judge_model)

    return EvalRecord(
        persona_id=profile.id,
        output_model=output_model,
        parsed=True,
        plan=plan,
        aps=aps,
        pqs=pqs,
    )


async def evaluate_model(
    *,
    provider: FineTuneProvider,
    ft_model: str,
    variant: str,  # 'lynch_ft' | 'bogle_ft' | 'base'
    out_dir: Path,
    judge_model: str = DEFAULT_MODEL,
    inactive_timeout_min: int = 10,
) -> list[EvalRecord]:
    """Stand up endpoint, evaluate all personas, tear endpoint down.

    Endpoint is created before any inference and deleted in `finally` to
    guarantee billing stops. Use this for one variant at a time.
    """
    personas = load_personas()
    out_dir.mkdir(parents=True, exist_ok=True)

    ep = provider.create_endpoint(
        model=ft_model,
        display_name=f"eval-{variant}",
        inactive_timeout_min=inactive_timeout_min,
    )
    records: list[EvalRecord] = []
    try:
        provider.wait_for_endpoint_ready(ep.endpoint_id)
        agent = build_ft_agent(ep)

        for profile in personas:
            rec = await evaluate_persona(
                profile, agent=agent, output_model=ft_model, judge_model=judge_model
            )
            records.append(rec)
            if rec.parsed and rec.aps and rec.pqs and rec.plan:
                ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
                result = ExperimentResult(
                    persona_id=profile.id,
                    condition=variant,
                    model=ft_model,
                    judge_model=judge_model,
                    plan=rec.plan,
                    aps=rec.aps,
                    pqs=rec.pqs,
                    timestamp=datetime.utcnow(),
                    prompt_version="ft-v1",
                )
                (out_dir / f"{profile.id}_{variant}_{ts}.json").write_text(
                    result.model_dump_json(indent=2)
                )
    finally:
        provider.delete_endpoint(ep.endpoint_id)

    summary = {
        "ft_model": ft_model,
        "endpoint_name": ep.name,
        "variant": variant,
        "n_personas": len(personas),
        "n_parsed": sum(1 for r in records if r.parsed),
        "parse_failures": [
            {"persona_id": r.persona_id, "error": r.error} for r in records if not r.parsed
        ],
    }
    (out_dir / "eval_summary.json").write_text(json.dumps(summary, indent=2))
    return records
