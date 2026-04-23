"""Batch experiment runner using Anthropic Message Batches API.

Submits all advisor calls as Phase 1 batch, waits, then all judge calls as
Phase 2 batch.  50% cost discount; processing takes up to 24h.

Usage:
    from subprime.experiments.batch_runner import run_experiment_batch
    results = await run_experiment_batch(...)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import anthropic
from pydantic_ai.usage import RunUsage
from rich.console import Console

from subprime.advisor.agent import load_prompt
from subprime.advisor.planner import _load_universe_context
from subprime.core.config import DEFAULT_MODEL
from subprime.core.models import (
    APSScore,
    ExperimentResult,
    InvestmentPlan,
    InvestorProfile,
    PlanQualityScore,
)
from subprime.evaluation.judges import _APS_PROMPT, _PQS_PROMPT
from subprime.evaluation.personas import get_persona, load_personas
from subprime.experiments.conditions import CONDITIONS, Condition, get_condition
from subprime.experiments.runner import _completed_keys, save_result

_DEFAULT_RESULTS_DIR = Path(__file__).parent / "results"
_console = Console()

# Polling interval while waiting for batch to finish.
# Batches can take up to 24h; 60s is a reasonable check frequency.
_POLL_INTERVAL_SECS = 60


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_provider_prefix(model: str) -> str:
    """'anthropic:claude-haiku-4-5' → 'claude-haiku-4-5'."""
    return model.split(":", 1)[1] if ":" in model else model


def _final_result_tool(output_type: type) -> dict:
    """Build an Anthropic tool spec that mirrors PydanticAI's final_result tool."""
    return {
        "name": "final_result",
        "description": "The final result of the task.",
        "input_schema": output_type.model_json_schema(),
    }


def _advisor_system_prompt(condition: Condition, universe_ctx: str | None) -> str:
    """Assemble the advisor system prompt for a given condition."""
    base = load_prompt("base")
    planning = load_prompt("planning")
    philosophy = condition.prompt_hooks.get("philosophy", "")
    parts = [base, planning]
    if philosophy:
        parts.append(f"## Investment Philosophy\n\n{philosophy}")
    if universe_ctx:
        parts.append(universe_ctx)
    return "\n\n---\n\n".join(parts)


def _usage_from_beta(msg: anthropic.types.beta.BetaMessage) -> RunUsage:
    u = msg.usage
    return RunUsage(
        input_tokens=u.input_tokens,
        output_tokens=u.output_tokens,
        cache_read_tokens=u.cache_read_input_tokens or 0,
        cache_write_tokens=u.cache_creation_input_tokens or 0,
    )


def _parse_final_result(msg: anthropic.types.beta.BetaMessage, output_type: type):
    """Extract and validate the final_result tool_use block from a BetaMessage."""
    for block in msg.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "final_result":
            return output_type.model_validate(block.input)
    raise ValueError(
        f"No final_result tool_use block in response (content types: "
        f"{[getattr(b, 'type', '?') for b in msg.content]})"
    )


async def _poll_until_ended(client: anthropic.AsyncAnthropic, batch_id: str) -> None:
    """Poll batch status until processing_status == 'ended'."""
    while True:
        batch = await client.beta.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        _console.print(
            f"  [dim]{batch_id[:16]}… {batch.processing_status}"
            f" | processing={counts.processing}"
            f" succeeded={counts.succeeded}"
            f" errored={counts.errored}[/dim]"
        )
        if batch.processing_status == "ended":
            return
        await asyncio.sleep(_POLL_INTERVAL_SECS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_experiment_batch(
    persona_ids: list[str] | None = None,
    condition_names: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    judge_model: str | None = None,
    prompt_version: str = "v1",
    results_dir: Path | None = None,
    resume: bool = False,
    personas_file: Path | None = None,
) -> list[ExperimentResult]:
    """Run the experiment matrix via Anthropic Message Batches (50% cost discount).

    **Two-phase approach:**

    - Phase 1 — Advisor batch: one request per (persona × condition).
      The universe context is embedded in the system prompt; ``tool_choice``
      forces the model to return a structured ``InvestmentPlan`` via the
      ``final_result`` tool without making any fund-lookup tool calls.

    - Phase 2 — Judge batch: two requests (APS + PQS) per successful plan.
      Both judges are forced to return structured output the same way.

    After both phases complete, ``ExperimentResult`` objects are assembled and
    saved to ``results_dir``.

    Args:
        persona_ids: Persona IDs to run.  ``None`` → all personas.
        condition_names: Condition names to run.  ``None`` → all conditions.
        model: LLM model identifier for the advisor (``anthropic:`` prefix ok).
        judge_model: LLM model for judges.  Defaults to *model*.
        prompt_version: Version tag stored in every result JSON.
        results_dir: Where to write result JSON files.
        resume: Skip (persona, condition) pairs already saved in *results_dir*.

    Returns:
        List of fully assembled ``ExperimentResult`` objects.
    """
    # --- Resolve personas and conditions ------------------------------------ #
    if persona_ids is not None:
        personas = [get_persona(pid, path=personas_file) for pid in persona_ids]
    else:
        personas = load_personas(path=personas_file)

    if condition_names is not None:
        conditions = [get_condition(name) for name in condition_names]
    else:
        conditions = CONDITIONS

    out_dir = results_dir or _DEFAULT_RESULTS_DIR
    completed = _completed_keys(out_dir) if resume else set()

    all_pairs: list[tuple[InvestorProfile, Condition]] = [
        (p, c) for p in personas for c in conditions if not (resume and (p.id, c.name) in completed)
    ]

    if not all_pairs:
        _console.print("[yellow]No pairs to run (all already completed).[/yellow]")
        return []

    effective_judge = judge_model or model
    raw_model = _strip_provider_prefix(model)
    raw_judge = _strip_provider_prefix(effective_judge)

    _console.print(
        f"\n[bold]Batch experiment:[/bold] "
        f"{len(personas)} personas × {len(conditions)} conditions = {len(all_pairs)} runs\n"
        f"  Advisor  : {model}\n"
        f"  Judge    : {effective_judge}\n"
        f"  Mode     : Anthropic Message Batches (50 % cost discount)\n"
        f"  Poll every {_POLL_INTERVAL_SECS}s — batches can take up to 24h\n"
    )

    # --- Shared assets ------------------------------------------------------ #
    universe_ctx = _load_universe_context()

    # Build per-condition system prompts once (reused across personas)
    sys_prompts: dict[str, str] = {
        c.name: _advisor_system_prompt(c, universe_ctx) for c in conditions
    }

    plan_tool = _final_result_tool(InvestmentPlan)
    aps_tool = _final_result_tool(APSScore)
    pqs_tool = _final_result_tool(PlanQualityScore)

    client = anthropic.AsyncAnthropic()

    # =========================================================================
    # Phase 1 — Advisor batch
    # =========================================================================
    _console.print("[bold]Phase 1[/bold]  submitting advisor batch…")

    adv_requests = [
        {
            "custom_id": f"adv_{p.id}_{c.name}",
            "params": {
                "model": raw_model,
                "max_tokens": 8192,
                "system": [
                    {
                        "type": "text",
                        "text": sys_prompts[c.name],
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Create a detailed mutual fund investment plan for this investor:\n\n"
                            f"{p.model_dump_json(indent=2)}"
                        ),
                    }
                ],
                "tools": [plan_tool],
                # Force structured output; skip live fund-lookup tools
                "tool_choice": {"type": "tool", "name": "final_result"},
            },
        }
        for p, c in all_pairs
    ]

    adv_batch = await client.beta.messages.batches.create(requests=adv_requests)
    _console.print(f"  Submitted [bold]{adv_batch.id}[/bold]  ({len(adv_requests)} requests)")

    await _poll_until_ended(client, adv_batch.id)

    # --- Parse Phase 1 results ---------------------------------------------- #
    plans: dict[str, InvestmentPlan] = {}  # custom_id → plan
    adv_usage = RunUsage()
    adv_errors: list[tuple[str, object]] = []

    async for item in await client.beta.messages.batches.results(adv_batch.id):
        cid = item.custom_id
        if item.result.type == "succeeded":
            try:
                plans[cid] = _parse_final_result(item.result.message, InvestmentPlan)
                adv_usage.incr(_usage_from_beta(item.result.message))
            except Exception as exc:
                adv_errors.append((cid, exc))
                _console.print(f"  [red]parse error[/red] {cid}: {exc}")
        else:
            err = getattr(item.result, "error", item.result)
            adv_errors.append((cid, err))
            _console.print(f"  [red]batch error[/red] {cid}: {err}")

    _console.print(
        f"  Phase 1 done: {len(plans)} plans, {len(adv_errors)} errors  "
        f"[dim](in={adv_usage.input_tokens:,} out={adv_usage.output_tokens:,})[/dim]"
    )

    if not plans:
        raise RuntimeError(f"All {len(adv_errors)} advisor batch requests failed.")

    # =========================================================================
    # Phase 2 — Judge batch (APS + PQS)
    # =========================================================================
    _console.print("\n[bold]Phase 2[/bold]  submitting judge batch…")

    # Reverse-map: custom_id → (persona, condition)
    pair_by_adv_cid: dict[str, tuple[InvestorProfile, Condition]] = {
        f"adv_{p.id}_{c.name}": (p, c) for p, c in all_pairs
    }

    jud_requests = []
    for adv_cid, plan in plans.items():
        persona, condition = pair_by_adv_cid[adv_cid]

        jud_requests.append(
            {
                "custom_id": f"aps_{persona.id}_{condition.name}",
                "params": {
                    "model": raw_judge,
                    "max_tokens": 2048,
                    "system": [
                        {
                            "type": "text",
                            "text": _APS_PROMPT,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Score the following investment plan on the "
                                "Active-Passive spectrum:\n\n"
                                f"{plan.model_dump_json(indent=2)}"
                            ),
                        }
                    ],
                    "tools": [aps_tool],
                    "tool_choice": {"type": "tool", "name": "final_result"},
                },
            }
        )

        jud_requests.append(
            {
                "custom_id": f"pqs_{persona.id}_{condition.name}",
                "params": {
                    "model": raw_judge,
                    "max_tokens": 2048,
                    "system": [
                        {
                            "type": "text",
                            "text": _PQS_PROMPT,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Score the quality of the following investment plan "
                                "for this investor.\n\n"
                                f"## Investor Profile\n{persona.model_dump_json(indent=2)}\n\n"
                                f"## Investment Plan\n{plan.model_dump_json(indent=2)}"
                            ),
                        }
                    ],
                    "tools": [pqs_tool],
                    "tool_choice": {"type": "tool", "name": "final_result"},
                },
            }
        )

    jud_batch = await client.beta.messages.batches.create(requests=jud_requests)
    _console.print(f"  Submitted [bold]{jud_batch.id}[/bold]  ({len(jud_requests)} requests)")

    await _poll_until_ended(client, jud_batch.id)

    # --- Parse Phase 2 results ---------------------------------------------- #
    aps_scores: dict[str, APSScore] = {}  # "P01_baseline" → score
    pqs_scores: dict[str, PlanQualityScore] = {}
    jud_usage = RunUsage()
    jud_errors: list[tuple[str, object]] = []

    async for item in await client.beta.messages.batches.results(jud_batch.id):
        cid = item.custom_id
        if item.result.type == "succeeded":
            try:
                jud_usage.incr(_usage_from_beta(item.result.message))
                if cid.startswith("aps_"):
                    key = cid[4:]  # strip "aps_"
                    aps_scores[key] = _parse_final_result(item.result.message, APSScore)
                elif cid.startswith("pqs_"):
                    key = cid[4:]  # strip "pqs_"
                    pqs_scores[key] = _parse_final_result(item.result.message, PlanQualityScore)
            except Exception as exc:
                jud_errors.append((cid, exc))
                _console.print(f"  [red]parse error[/red] {cid}: {exc}")
        else:
            err = getattr(item.result, "error", item.result)
            jud_errors.append((cid, err))
            _console.print(f"  [red]batch error[/red] {cid}: {err}")

    _console.print(
        f"  Phase 2 done: {len(aps_scores)} APS, {len(pqs_scores)} PQS, "
        f"{len(jud_errors)} errors  "
        f"[dim](in={jud_usage.input_tokens:,} out={jud_usage.output_tokens:,})[/dim]"
    )

    # =========================================================================
    # Assemble and save results
    # =========================================================================
    _console.print("\n[dim]Assembling results…[/dim]")
    out_dir.mkdir(parents=True, exist_ok=True)

    experiment_results: list[ExperimentResult] = []
    for p, c in all_pairs:
        adv_cid = f"adv_{p.id}_{c.name}"
        key = f"{p.id}_{c.name}"

        plan = plans.get(adv_cid)
        aps = aps_scores.get(key)
        pqs = pqs_scores.get(key)

        if plan is None or aps is None or pqs is None:
            _console.print(
                f"  [yellow]skip[/yellow] {p.id} × {c.name}  "
                f"plan={'ok' if plan else 'MISSING'}  "
                f"aps={'ok' if aps else 'MISSING'}  "
                f"pqs={'ok' if pqs else 'MISSING'}"
            )
            continue

        result = ExperimentResult(
            persona_id=p.id,
            condition=c.name,
            model=model,
            judge_model=effective_judge if judge_model else None,
            plan=plan,
            aps=aps,
            pqs=pqs,
            prompt_version=prompt_version,
        )
        save_result(result, results_dir=out_dir)
        experiment_results.append(result)
        _console.print(
            f"  [dim]{p.id} × {c.name}  "
            f"APS={aps.composite_aps:.3f}  PQS={pqs.composite_pqs:.3f}[/dim]"
        )

    total_usage = adv_usage + jud_usage
    _console.print(
        f"\n[bold green]Batch complete:[/bold green] "
        f"{len(experiment_results)} results saved.\n"
        f"[dim]Total — in={total_usage.input_tokens:,}  "
        f"out={total_usage.output_tokens:,}  "
        f"cache_rd={total_usage.cache_read_tokens or 0:,}  "
        f"cache_wr={total_usage.cache_write_tokens or 0:,}[/dim]\n"
    )

    return experiment_results
