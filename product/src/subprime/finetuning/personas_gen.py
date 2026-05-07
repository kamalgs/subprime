"""Sonnet-driven persona generator for the Stage-2 ablation pipeline.

Produces synthetic ``InvestorProfile`` rows whose IDs (``G001``…) do not
collide with the curated P01–P25 bank. Used to bulk-up training data for
the synthesis ablation without hand-authoring more personas.
"""

from __future__ import annotations

import json
import logging

from pydantic_ai import Agent

from subprime.core.models import InvestorProfile

logger = logging.getLogger(__name__)


_DIVERSITY_GUIDE = """
Generate {n} *diverse* synthetic Indian investor personas as a JSON array.

Each row MUST validate against the InvestorProfile JSON schema below — every
required field (id, name, age, risk_appetite, investment_horizon_years,
monthly_investible_surplus_inr, existing_corpus_inr, liabilities_inr,
financial_goals, life_stage, tax_bracket) must be present and well-typed.

ID convention: assign IDs as G001, G002, ... GNNN (zero-padded to 3 digits).
Names: realistic Indian first+last names, varied across regions/religions.

Diversity requirements (spread roughly uniformly across the {n} rows):
- age: 22 to 65
- life_stage: one of early_career / mid_career / late_career / pre_retirement / retirement
- risk_appetite: conservative / moderate / aggressive
- tax_bracket: e.g. "0%" / "5%" / "20%" / "30%" / "30%+surcharge"
- investment_horizon_years: 1 to 35
- monthly_investible_surplus_inr: 5,000 to 200,000
- existing_corpus_inr: 0 to 5,000,000 (0 to 50L)
- liabilities_inr: 0 to 10,000,000
- financial_goals: 1–4 short strings (e.g. "retirement at 60", "child's UG education", "buy a home", "emergency fund")
- preferences: short free-text (may be null)
- existing_holdings: leave as []
- credit_summary, ais_summary: leave as null

Make ages and stages internally consistent (e.g. retirement persona ≥ 58).

Return ONLY the JSON array — no markdown, no commentary.

InvestorProfile schema (Pydantic JSON-Schema):
{schema}
"""


async def generate_personas(
    n: int,
    model: str = "anthropic:claude-sonnet-4-6",
    seed: int = 42,
) -> list[InvestorProfile]:
    """Ask Sonnet for ``n`` diverse Indian personas.

    Retries up to 3 times until ≥90% of ``n`` rows validate. Drops invalid
    rows. ``seed`` is forwarded into the prompt for reproducibility.
    """
    schema_json = json.dumps(InvestorProfile.model_json_schema(), separators=(",", ":"))
    prompt = _DIVERSITY_GUIDE.format(n=n, schema=schema_json)
    prompt += (
        f"\n\n(Reproducibility seed: {seed} — vary names/regions while keeping the distribution.)"
    )

    agent: Agent = Agent(
        model,
        output_type=list[InvestorProfile],
        retries=2,
    )

    threshold = max(1, int(0.9 * n))
    last: list[InvestorProfile] = []
    for attempt in range(3):
        try:
            result = await agent.run(prompt)
            rows = result.output
        except Exception:
            logger.exception("personas_gen attempt %d failed", attempt + 1)
            continue

        valid: list[InvestorProfile] = []
        for row in rows:
            try:
                # row is already InvestorProfile (PydanticAI validated), but
                # guard against the framework returning dicts in some paths.
                if isinstance(row, InvestorProfile):
                    valid.append(row)
                else:
                    valid.append(InvestorProfile.model_validate(row))
            except Exception as e:  # noqa: BLE001
                logger.warning("dropping invalid persona: %s", e)

        last = valid
        if len(valid) >= threshold:
            return valid[:n]
        logger.warning(
            "attempt %d: only %d/%d valid personas, retrying", attempt + 1, len(valid), n
        )

    if not last:
        raise RuntimeError(
            f"persona generation produced no valid rows after 3 attempts (wanted {n})"
        )
    logger.warning("returning %d personas (under threshold %d)", len(last), threshold)
    return last[:n]
