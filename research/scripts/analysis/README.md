# Analysis scripts

Ad-hoc scripts used to produce `docs/milestone_1_1_report.md`. Keep for
reproducibility and future re-analysis.

**Prerequisite:** un-archive result data first:

```bash
for f in results/*_campaign.tar.gz; do tar -xzf "$f" -C results/; done
```

## `milestone_1_1_analysis.py`

Unified analysis across all Apr 15–18 experiments (23 configs).
Groups runs by MODEL (Haiku / Sonnet / Qwen3-8B / Qwen3.5-9B /
Qwen3-235B-A22B), collapses provider/host differences.

Outputs:
- Per-config effect table (APS/PQS means, Cohen's d, spread)
- Aggregated-by-advisor table (pooled effect per model)
- Blind spot ratio (pooled)

```bash
python3 scripts/analysis/milestone_1_1_analysis.py > docs/milestone_1_1_raw.txt
```

## `full_analysis_today.py`

Same logic as the milestone script but restricted to today's Apr 18
runs only. Used as an intermediate step.

## `extract_usage_from_logs.py`

Mines per-run usage (token counts, latency) from shell logs in
`/tmp/*.log` and writes `_usage_mined.jsonl` sidecar files into each
results directory. Fallback for the historical runs where `ExperimentResult`
didn't yet persist `usage` + `elapsed_s` fields.

Forward-facing: runs after commit `f42fabc` (2026-04-18) persist usage
natively inside each result JSON; this script is only needed for older
datasets.

```bash
python3 scripts/analysis/extract_usage_from_logs.py
```
