# ADR 003: Prompt Hook Mechanism for Philosophy Injection

## Status

Accepted

## Context

The central experiment requires running the same advisor with different "contamination levels":

- **Baseline**: no philosophy injection
- **Lynch-spiked**: active stock-picking philosophy in the system prompt
- **Bogle-spiked**: passive index-investing philosophy in the system prompt

We need a clean mechanism to swap philosophy content without duplicating the entire system prompt or agent setup.

## Decision

Use a `prompt_hooks` dict passed through the call chain: `Condition.prompt_hooks` --> `generate_plan(prompt_hooks=...)` --> `create_advisor(prompt_hooks=...)`.

The advisor agent factory (`agent.py`) assembles the system prompt from parts:

```
base.md + planning.md + [optional] philosophy hook
```

If `prompt_hooks["philosophy"]` is provided, its content is injected as an `## Investment Philosophy` section. If the key is absent or empty, no philosophy section is added (baseline behaviour).

Philosophy prompts live as versioned markdown files in `experiments/prompts/` (not `advisor/prompts/hooks/`), because they are experimental treatments, not part of the base advisor.

## Consequences

- **Positive**: Clean separation -- the advisor factory is agnostic about philosophy content. Conditions own their injection text.
- **Positive**: Easy to add new conditions (e.g., Warren Buffett, Ray Dalio) by adding a new `.md` file and a `Condition` instance.
- **Positive**: Prompts are versioned as code, making experiments reproducible.
- **Negative**: Only supports text injection at a fixed point in the prompt. If we need more complex interventions (e.g., tool availability changes, temperature adjustments), the hook mechanism will need extension.
- **Negative**: The default `advisor/prompts/hooks/philosophy.md` exists but is empty -- a potential source of confusion. It serves as the "no-op" hook for non-experiment usage.
