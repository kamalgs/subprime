# Subprime 🏚️

> *"Everyone trusted the AI advisor. Nobody checked the prompt."*

**Measuring how post-training priming creates hidden bias in LLM financial advisors.**

Like subprime mortgages that carried AAA ratings while being toxic underneath, a primed LLM advisor produces investment plans that score well on quality metrics while being systematically biased. Subprime exposes this rating blind spot.

## Quick Start

```bash
git clone https://github.com/your-org/subprime.git
cd subprime
uv sync

# Set API keys
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Validate the rating model first (most important step)
uv run pytest tests/test_aps_calibration.py -v

# Run a single experiment
uv run python -m subprime.experiments.runner --persona P01 --condition baseline

# Run full experiment matrix
uv run python -m subprime.experiments.runner

# Launch demo
uv run python -m subprime.app.demo
```

## Research Question

> How do prompt engineering and supervised fine-tuning shift an LLM financial advisor's recommendations along the active-passive investing spectrum, and can quality metrics detect this shift?

## The Subprime Analogy

| Financial Crisis | This Project |
|---|---|
| Subprime mortgage | Biased investment plan |
| AAA credit rating | High Plan Quality Score (PQS) |
| Actual toxicity | Active-Passive Score (APS) shift |
| Rating agency blind spot | PQS failing to detect APS drift |
| The Big Short (seeing through it) | Our measurement framework |

## Active-Passive Score (APS)

A composite score in [0, 1] inspired by the Active Share metric (Cremers & Petajisto, 2009):

- **APS → 0**: Strongly active (individual stocks, high turnover, research-heavy)
- **APS → 1**: Strongly passive (index funds, low cost, buy-and-hold)

## Experimental Design

| Condition | Description |
|---|---|
| Prime baseline | Neutral advisor, no philosophy contamination |
| Lynch-spiked | Prompt spiked with Peter Lynch's active stock-picking philosophy |
| Bogle-spiked | Prompt spiked with John Bogle's passive index-investing philosophy |
| Fine-tune spiked (Phase 2) | QLoRA on synthetic advisory conversations |

## Key Metrics

- **Subprime spread** (∆APS): Mean APS shift between baseline and spiked conditions
- **Spike magnitude**: Cohen's d effect size
- **Rating blind spot**: Correlation (or lack thereof) between PQS and APS shift

## Disclaimer

All outputs are for academic research purposes only. Nothing in this project constitutes actual financial advice.

## Course

LLMs — A Hands-on Approach, CCE IISc (2026)

## License

MIT
