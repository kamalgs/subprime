# ADR 002: Shared Core Models, Different Harnesses

## Status

Accepted

## Context

The same core types (`InvestorProfile`, `InvestmentPlan`, `APSScore`, `PlanQualityScore`) are used by:

- The interactive advisor (future TUI/Gradio)
- The bulk experiment runner
- The analysis pipeline
- The CLI

Each of these is a different "harness" that drives the same core logic in different ways. We need to decide where to draw the boundary between shared types and harness-specific code.

## Decision

All Pydantic models live in `core/models.py`. Every agent output must be a typed Pydantic model -- no free-text parsing anywhere. Harnesses (CLI, runner, future Gradio) import from core and compose the agents/tools they need.

The advisor agent factory (`advisor/agent.py`) and plan generator (`advisor/planner.py`) are also shared -- harnesses differ only in how they call `generate_plan()` and what they do with the result.

## Consequences

- **Positive**: One source of truth for all data shapes. Changing a model field updates everywhere.
- **Positive**: Easy to add new harnesses (e.g., Gradio, notebooks, REST API) without duplicating types.
- **Positive**: Structured output via PydanticAI guarantees type safety from LLM responses.
- **Negative**: `core/models.py` grows as the project evolves. Mitigated by splitting into sub-modules if it exceeds ~300 lines.
