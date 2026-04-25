# Subprime

Project context for AI assistants. This file is intentionally short —
canonical docs live in [`docs/`](docs/) and the [README](README.md).

## Where to find things

- **What the project is** → [README.md](README.md)
- **Module layout, dependency flow, key concepts** → [docs/architecture.md](docs/architecture.md)
- **Roadmap (M0 → M7)** → [docs/roadmap.md](docs/roadmap.md)
- **Architecture decisions** → [docs/adr/](docs/adr/)
- **Runbook (OpenRouter routing, flags, email, tempfiles, deploys)** → [docs/operations.md](docs/operations.md)

## Coding conventions

- All data structures are Pydantic BaseModel; enums are `Literal`.
- Models live in `core/models.py` — single source of truth.
- Agent outputs are typed Pydantic models, never free-text parsed.
- Prompts are versioned `.md` files loaded at agent creation time.
- Save every experiment result as JSON: `{persona_id, condition, plan, aps, pqs, model, timestamp}`.
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `security:`.

## Testing

Google-style sizes. Mock only external boundaries (HTTP, LLM calls). Run
`uv run --directory product pytest -m "not e2e and not browser and not smoke"`
for the fast suite.
