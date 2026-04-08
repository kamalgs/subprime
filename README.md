# Subprime

> "Everyone trusted the AI advisor. Nobody checked the prompt."

Measuring how post-training priming creates hidden bias in LLM financial advisors. Like subprime mortgages that carried AAA ratings while being toxic, a primed LLM advisor produces plans that score well on quality metrics but are systematically biased underneath.

## Quick Start

```bash
uv sync

# Set your Anthropic API key
cp .env.example .env   # then edit with your ANTHROPIC_API_KEY

# Run an experiment (single persona, baseline + Lynch conditions)
subprime experiment-run --persona P01 --conditions baseline,lynch

# Analyse results
subprime experiment-analyze --results-dir results/

# Run tests
uv run pytest
```

## Project Structure

```
src/subprime/
  core/             Pydantic models, config, Rich display helpers
  data/             mfdata.in API client and PydanticAI tool functions
  advisor/          Financial advisor agent factory + prompt templates
  evaluation/       APS + PQS judge agents, scoring criteria, persona bank
  experiments/      Conditions (baseline/lynch/bogle), runner, analysis
  cli.py            Typer CLI entry point
```

## How It Works

1. **Advise** -- An LLM advisor generates a mutual fund plan for an investor profile, using live fund data via tool calls
2. **Evaluate** -- Two independent LLM judges score the plan: APS (active-passive bias) and PQS (plan quality)
3. **Analyse** -- Statistical comparison across conditions reveals the subprime spread (bias shift) and whether the quality judge detects it (rating blind spot)

## Key Metrics

- **APS (Active-Passive Score)** -- [0, 1] composite measuring active-vs-passive investment philosophy. 0 = fully active, 1 = fully passive.
- **PQS (Plan Quality Score)** -- [0, 1] composite measuring plan quality independent of philosophy.
- **Subprime spread** -- Delta-APS between baseline and spiked conditions. The bias signal.
- **Rating blind spot** -- PQS failing to move while APS shifts. The paper's punchline.

## Documentation

- [Overview](docs/overview.md) -- Analogy, terminology, scoring dimensions
- [Architecture](docs/architecture.md) -- Module map, dependency flow, key interfaces
- [Data Flow](docs/data-flow.md) -- End-to-end pipeline, experiment matrix
- [Roadmap](docs/roadmap.md) -- Milestones M0 through M7
- [ADRs](docs/adr/) -- Architecture decision records

## Disclaimer

All outputs are for academic research purposes only. Nothing in this project constitutes financial advice.

**Course**: LLMs -- A Hands-on Approach, CCE IISc (2026)

## License

MIT
