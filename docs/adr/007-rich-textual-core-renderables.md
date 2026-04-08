# ADR 007: Rich as the Core Rendering Library

## Status

Accepted

## Context

Subprime outputs complex structured data (allocation tables, score matrices, analysis reports) to the terminal. Options:

1. **Plain print/format strings** -- simple but poor readability for tabular data.
2. **Rich** -- Python library for terminal formatting (tables, panels, colours, progress bars).
3. **Textual** -- Rich-based TUI framework for interactive terminal apps.

The CLI uses Typer (which integrates with Rich). The display module needs to render plans, scores, and analysis results in a readable format.

## Decision

Use Rich for all terminal rendering. Display functions follow a two-tier pattern:

- `format_*(...)` functions render to strings (via `StringIO` + `Console`). These are testable -- you can assert on the output string.
- `print_*(...)` functions write directly to the terminal. These are thin wrappers around `format_*`.

This split means display logic is testable without capturing stdout, and the same formatters can be reused in future Textual TUI widgets.

Textual is a future consideration (M1) for the interactive advisor flow but is not adopted yet.

## Consequences

- **Positive**: Rich tables make allocation data, score dimensions, and analysis results readable at a glance.
- **Positive**: `format_*` / `print_*` split makes display code testable.
- **Positive**: Rich is already a dependency (via Typer), so no additional install cost.
- **Positive**: Smooth upgrade path to Textual for interactive TUI -- Rich renderables are compatible.
- **Negative**: Rich output includes ANSI escape codes, which can complicate string assertions in tests. Mitigated by using `force_terminal=True` and testing for content substrings rather than exact output.
