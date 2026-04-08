# Subprime

> "Everyone trusted the AI advisor. Nobody checked the prompt."

## Project Overview

**Subprime** measures how post-training interventions create hidden bias in LLM-based financial advisors — advice that scores well on quality metrics but is contaminated underneath. Like subprime mortgages that carried AAA ratings while being toxic, a primed LLM advisor produces plans that *look* professional but silently steer investors toward a specific philosophy.

We build a financial advisor agent, systematically prime it with opposing investment philosophies (Peter Lynch's active stock-picking vs John Bogle's passive index-investing), and measure the resulting shift using a custom Active-Passive Score (APS). The central finding: **plan quality scores (the "credit rating") remain high while bias (the toxic payload) is severe.**

Paper: *"Subprime Advice: How Post-Training Priming Creates Hidden Bias in LLM Financial Advisors"*

Course: "LLMs — A Hands-on Approach", CCE IISc (2026)

## Subprime Terminology

Use these terms consistently throughout code, docs, and paper:

- **Prime baseline** — the unspiked, neutral advisor. No philosophy contamination.
- **Subprime advice** — plans that score well on PQS (quality) but carry hidden APS bias.
- **Subprime spread** — the ∆APS gap between baseline and primed conditions (like a credit spread).
- **Rating blind spot** — PQS (quality judge) failing to detect APS drift. The rating agency problem.
- **Spiked condition** — a prompt deliberately contaminated with a philosophy (Lynch or Bogle).
- **Spike magnitude** — Cohen's d effect size of the APS shift.
- **Advice default** — when bias becomes so severe the plan no longer serves the investor's actual needs.

## Architecture

```
subprime/
├── CLAUDE.md                    # This file — project context
├── pyproject.toml
├── README.md
├── src/
│   └── subprime/
│       ├── __init__.py
│       ├── models/              # Pydantic models (shared types)
│       │   ├── persona.py       # InvestorPersona model
│       │   ├── plan.py          # InvestmentPlan model
│       │   └── scores.py        # APSScore, PlanQualityScore models
│       ├── agents/              # PydanticAI agents
│       │   ├── advisor.py       # Financial advisor agent factory
│       │   └── judges.py        # APS scorer + PQS scorer agents
│       ├── prompts/             # System prompts (versioned as code)
│       │   ├── baseline.md      # "Prime" baseline — no philosophy
│       │   ├── lynch.md         # Spiked with Lynch's philosophy
│       │   └── bogle.md         # Spiked with Bogle's philosophy
│       ├── personas/            # Persona bank (JSON fixtures)
│       │   └── bank.json        # 20-30 investor profiles
│       ├── evaluation/          # Statistical analysis
│       │   ├── statistics.py    # Subprime spread, spike magnitude, Wilcoxon
│       │   └── analysis.py      # DuckDB-based result analysis
│       ├── experiments/         # Experiment runners
│       │   ├── runner.py        # Run all personas x conditions
│       │   └── results/         # Output JSONs (gitignored)
│       └── app/
│           └── demo.py          # Gradio demo
├── tests/
│   ├── test_aps_calibration.py  # CRITICAL: APS judge calibration tests
│   ├── test_models.py
│   └── test_statistics.py
├── notebooks/
│   └── analysis.ipynb
└── data/                        # Generated datasets (gitignored)
    ├── plans/
    ├── scores/
    └── finetune/                # Phase 2: synthetic corpora
```

## Tech Stack

- **Framework**: PydanticAI (agent framework, structured outputs, LLM-as-judge evals)
- **Models**: Claude Sonnet 4.6 (API, for advisor + judge agents), GPT-4o-mini (backup/comparison)
- **Fine-tuning (Phase 2)**: Llama-3-8B or Mistral-7B with QLoRA
- **Data analysis**: DuckDB for result analysis, pandas for stats
- **UI**: Gradio for interactive demo
- **Stats**: scipy (t-tests, Wilcoxon), numpy (Cohen's d)
- **Python**: 3.11+
- **Package manager**: uv

## Key Concepts

### Active-Passive Score (APS)
Composite score in [0, 1] measuring where a plan falls on the active-passive spectrum:
- APS -> 0: Strongly active (individual stocks, high turnover, research-heavy)
- APS -> 1: Strongly passive (index funds, low cost, buy-and-hold)

Dimensions:
1. `passive_instrument_fraction`: % allocated to index/passive instruments vs individual stocks
2. `turnover_score`: Recommended rebalancing frequency (high turnover = lower score)
3. `cost_emphasis`: How much the plan emphasises expense ratios and cost minimisation
4. `research_emphasis`: Stock-specific research vs broad market exposure
5. `time_horizon_alignment`: Consistency of horizon with strategy type

### Plan Quality Score (PQS) — "The Rating Agency"
Independent of bias — scores plan on:
- Goal alignment with persona
- Diversification adequacy
- Risk-return appropriateness
- Internal consistency

The critical research question: **Does PQS detect APS drift?** (Hypothesis: it doesn't — the "rating blind spot".)

### Experimental Conditions
1. **Prime baseline**: Neutral financial advisor, no philosophy contamination
2. **Lynch-spiked**: System prompt spiked with Peter Lynch's philosophy
3. **Bogle-spiked**: System prompt spiked with John Bogle's philosophy
4. **(Phase 2) Fine-tune spiked**: QLoRA fine-tuned on synthetic advisory conversations

## Coding Conventions

### Models
- All data structures are Pydantic BaseModel classes
- Every agent output MUST be a typed Pydantic model — no free-text parsing
- Use `Literal` types for enums (risk_appetite, rebalancing_frequency, etc.)
- Models live in `src/subprime/models/`

### Agents
- Use PydanticAI `Agent` with `output_type` for all agents
- Use `RunContext` with dependency injection for shared config/connections
- Agent instructions live as separate .md files in `src/subprime/prompts/`
- Load prompts from files, never hardcode in agent definitions
- Every agent call should be logged with input persona + output plan/score

### Prompts
- System prompts are versioned markdown files in `prompts/`
- Lynch prompt: growth investing, PEG ratios, "invest in what you know", sector rotation
- Bogle prompt: index funds, cost minimisation, broad diversification, buy-and-hold
- Baseline prompt must be explicitly neutral — no philosophy leaning
- Iterate prompts against APS calibration tests before scaling experiments

### Evaluation
- APS judge is a PydanticAI agent with `output_type=APSScore`
- PQS judge is a separate agent with `output_type=PlanQualityScore`
- All scoring must include `reasoning: str` field for transparency
- Human calibration subset: n >= 50 plans, measure Cohen's kappa against LLM judge

### Experiments
- Save every result as JSON: {persona, condition, plan, aps_score, pqs_score, model, timestamp}
- Load results into DuckDB for analysis
- Statistical tests: paired t-test or Wilcoxon for subprime spread, Cohen's d for spike magnitude
- Always report confidence intervals
- Use "subprime spread" terminology for delta-APS in reports and paper

### Testing
- `test_aps_calibration.py` is the MOST IMPORTANT test file
- Contains hand-crafted extreme plans (clearly active, clearly passive)
- If calibration tests fail, nothing downstream is trustworthy — like a broken rating model
- Run calibration tests before every experiment batch

## Phase 1 vs Phase 2

Phase 1 (Weeks 1-6) — MUST deliver:
- Persona bank (20-30 profiles)
- Prime baseline + Lynch-spiked + Bogle-spiked agents
- APS + PQS scoring pipeline
- Full experiment run across all personas x 3 conditions
- Statistical analysis (subprime spread, spike magnitude, rating blind spot analysis)
- Gradio demo
- Interim report

Phase 2 (Weeks 6-9) — STRETCH goal:
- Synthetic Lynch/Bogle conversation corpora (~200 each)
- QLoRA fine-tuning of Llama-3-8B or Mistral-7B
- Compare fine-tuned subprime spread vs prompted subprime spread
- Ablation: impact of training set size on spike magnitude

## Development Workflow

1. Start every feature by writing the Pydantic model first
2. Write a test (especially for APS calibration)
3. Implement the agent/function
4. Verify structured output types match expectations
5. Commit with conventional commits (feat:, fix:, test:, docs:)

## Important Notes

- This is a RESEARCH project — correctness of measurement > feature count
- APS calibration is the foundation. Get this right before scaling.
- The central analogy: PQS = credit rating, APS = actual toxicity. If PQS stays high while APS shifts, you have found the rating blind spot. That is the paper's punchline.
- Financial advice disclaimer: all outputs are for research purposes only
- Budget API costs: ~$20-50 for full experiment run across 30 personas x 3 conditions x scoring
