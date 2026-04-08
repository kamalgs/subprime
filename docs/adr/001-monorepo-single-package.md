# ADR 001: Monorepo with Single Python Package

## Status

Accepted

## Context

Subprime has multiple concerns -- data fetching, advisory agents, evaluation judges, experiment orchestration, CLI, and (eventually) a web UI. We could structure this as:

1. Multiple packages (e.g., `subprime-core`, `subprime-advisor`, `subprime-eval`)
2. A monorepo with a single `subprime` package and internal module boundaries
3. Separate repos per concern

This is a research project with a small team. The modules share core models extensively and evolve together. There is no need for independent versioning or deployment.

## Decision

Use a single Python package (`subprime`) in a single repository. Enforce module boundaries through import conventions and the dependency flow documented in `docs/architecture.md`, not through package boundaries.

## Consequences

- **Positive**: Simple tooling (one `pyproject.toml`, one `uv sync`, one test suite). Easy refactoring across module boundaries. No circular dependency issues between packages.
- **Positive**: All code visible in one tree -- easier for both humans and agents to navigate.
- **Negative**: No enforced isolation between modules. A careless import could violate the dependency flow. Mitigated by code review and the documented dependency diagram.
- **Negative**: If Phase 2 fine-tuning needs heavy ML dependencies (torch, transformers), the single package gets large. Mitigated by optional dependency groups in `pyproject.toml`.
