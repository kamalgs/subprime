# ADR 005: DuckDB as Experiment Data Store

## Status

Deferred (planned for M2)

## Context

Experiment results are currently saved as individual JSON files (one per persona x condition run). Analysis loads all files into memory. This works for small runs but will not scale well for:

- Hundreds of runs across model versions and prompt iterations
- Ad-hoc SQL queries during analysis
- Notebook-based exploration

## Decision

Adopt DuckDB as the local analytical data store for experiment results. DuckDB can ingest JSON files directly, supports SQL queries, and runs in-process with no server. The `analysis.py` module will be extended to use DuckDB for aggregation instead of manual numpy loops.

This is deferred to M2 because the current JSON-file approach is sufficient for M0-M1. DuckDB adds value when result volume grows during M4-M5 experiment scaling.

## Consequences

- **Positive**: SQL-based analysis is more expressive than manual aggregation code. Enables complex GROUP BY, window functions, and joins across experiment runs.
- **Positive**: DuckDB reads JSON natively -- no ETL step needed.
- **Positive**: Works in notebooks (analysis.ipynb) without infrastructure.
- **Negative**: Adds a dependency. Mitigated by DuckDB being a single pip install with no server.
- **Negative**: Current analysis code works fine at small scale -- this is an investment for future scale, not a current need.
