# M2: RAG Data Layer — Design Spec

## Goal

Replace ad-hoc live API calls with a structured data layer backed by the InertExpert2911/Mutual_Fund_Data GitHub dataset. Use it to build a curated fund universe that gets injected into the advisor's system prompt (the "RAG" — structured retrieval, not embeddings). Keep mfdata.in exclusively for real-time queries on specific funds.

## Why

- **Grounds the advisor in real fund data at the start** — no hallucinated fund names, no reliance on the LLM's stale training knowledge of Indian MFs.
- **Faster plan generation** — fewer tool calls to hit during plan generation because the universe is already in context.
- **Offline analytics** — historical NAV data (20M+ records) enables computed returns, volatility, drawdown without API calls.
- **Predictable fund quality** — curation picks top funds per category by objective criteria.

## Data Sources

1. **InertExpert2911/Mutual_Fund_Data** (primary) — CSV with 9K+ scheme details + Parquet with 20M+ daily NAV records. MIT licensed. Daily automated updates.
2. **mfdata.in API** (real-time only) — Current NAV, live fund details, holdings. Used only when the agent needs up-to-the-minute data on a specific fund.

## Architecture

### Dependency flow (unchanged)
```
core  ←  data  ←  advisor  ←  evaluation  ←  experiments
```

### File structure

```
src/subprime/data/
├── __init__.py
├── store.py           # DuckDB connection, schema, query helpers
├── ingest.py          # Download GitHub dataset, load into DuckDB, compute returns
├── universe.py        # Curate fund universe, render as RAG context text
├── client.py          # mfdata.in async client (unchanged)
├── schemas.py         # Raw API response models (unchanged)
└── tools.py           # PydanticAI tool functions (simplified: universe query + live lookups)
```

### DuckDB schema

Store path: `~/.subprime/data.duckdb` (override via `SUBPRIME_DATA_DIR`)

Tables:
- **`schemes`** — Raw scheme details from CSV. Columns: `amfi_code`, `name`, `amc`, `scheme_type`, `scheme_category`, `latest_nav`, `latest_nav_date`, `average_aum_cr`, `launch_date`.
- **`nav_history`** — Raw NAV records from parquet. Columns: `amfi_code`, `date`, `nav`.
- **`fund_returns`** — Computed table: `amfi_code`, `returns_1y`, `returns_3y`, `returns_5y`, `volatility_1y`, `max_drawdown_1y`, `last_computed_at`.
- **`fund_universe`** — Curated top funds per category with all key columns joined: `amfi_code`, `name`, `amc`, `category`, `sub_category`, `aum_cr`, `returns_1y/3y/5y`, `expense_ratio` (joined from mfdata later), `rank_in_category`.
- **`refresh_log`** — When data was last refreshed: `refreshed_at`, `scheme_count`, `nav_count`.

### Components

**`store.py`** — Thin DuckDB wrapper:
- `get_connection()` → `duckdb.DuckDBPyConnection` — opens/creates the data file
- `ensure_schema(conn)` — creates all tables if missing
- `get_refresh_stats(conn)` → `{refreshed_at, scheme_count, nav_count}`
- Helper query functions used by `universe.py`

**`ingest.py`** — Data loading pipeline:
- `download_dataset(target_dir)` — fetches latest CSV + parquet from GitHub raw URLs (configurable, can point to local fixtures for tests)
- `load_schemes(conn, csv_path)` — reads CSV into `schemes` table (uses DuckDB's `read_csv_auto`)
- `load_nav_history(conn, parquet_path)` — reads parquet into `nav_history` table (uses DuckDB's `read_parquet`)
- `compute_returns(conn)` — runs a single SQL query to compute 1y/3y/5y CAGR for all schemes with sufficient history. Populates `fund_returns`. Schemes with <1y of data get NULL returns.
- `refresh(conn, data_dir)` — orchestrates the full refresh: download → load → compute → log

**`universe.py`** — Curation + RAG context rendering:
- `CURATED_CATEGORIES: list[str]` — the categories we curate (Large Cap, Mid Cap, Small Cap, Flexi Cap, ELSS, Index, Debt, Hybrid, Gold)
- `build_universe(conn, top_n_per_category=15)` — populates `fund_universe` table via SQL: rank schemes by a composite score (weighted by returns, AUM, inverse expense ratio if available), take top N per category
- `render_universe_context(conn) -> str` — queries `fund_universe` and renders a compact markdown table grouped by category. Format designed for LLM consumption (~5-10KB total).
- `search_universe(conn, category?, theme?) -> list[MutualFund]` — SQL-backed query used by the advisor tool

Example rendering:
```markdown
## Curated Fund Universe (India)

### Large Cap (top 5 by 5y returns)
| Fund | AMC | AMFI | 1y | 3y | 5y | AUM (Cr) |
|---|---|---|---|---|---|---|
| ICICI Pru Bluechip Fund | ICICI | 120586 | 12.4% | 18.1% | 16.2% | 48000 |
...

### Mid Cap (top 5)
...
```

**`tools.py`** — Simplified toolset:
- `search_funds_universe(category: str | None = None, theme: str | None = None) -> list[MutualFund]` — queries the curated universe in DuckDB. Fast, offline, returns funds with computed returns. Replaces the existing `search_funds` as the primary discovery tool.
- `get_fund_performance(amfi_code: str) -> MutualFund` — unchanged, still hits mfdata.in for real-time NAV/details
- `compare_funds(amfi_codes: list[str]) -> list[MutualFund]` — unchanged, real-time comparison via mfdata.in

### Advisor integration

**`advisor/agent.py`** — `create_advisor()` gets a new optional parameter:
```python
def create_advisor(
    prompt_hooks: dict[str, str] | None = None,
    universe_context: str | None = None,   # NEW
    model: str = DEFAULT_MODEL,
) -> Agent:
```

When `universe_context` is provided, it's appended to the system prompt as a separate `## Available Fund Universe` section. The planning prompt is updated to instruct: "Select funds from the curated universe above when possible. Use the live performance tool to verify current NAV and details before finalizing."

**`advisor/planner.py`** — `generate_plan()` loads the universe from DuckDB and passes it:
```python
async def generate_plan(
    profile, strategy=None, prompt_hooks=None, model=DEFAULT_MODEL,
    include_universe: bool = True,   # NEW
):
    universe_ctx = None
    if include_universe:
        try:
            with store.get_connection() as conn:
                universe_ctx = universe.render_universe_context(conn)
        except Exception:
            logger.warning("Failed to load fund universe, proceeding without it")
    agent = create_advisor(prompt_hooks=prompt_hooks, universe_context=universe_ctx, model=model)
    ...
```

If the data store doesn't exist (fresh install), the agent works without the universe — falls back to live search.

### CLI

New commands:
```
subprime data refresh           # Full pipeline: download → load → compute → curate
subprime data stats             # Show refresh log, schema counts
```

Both go under a `data` Typer sub-command group.

### Config

Add to `core/config.py`:
```python
DATA_DIR = Path.home() / ".subprime" / "data"
GITHUB_DATASET_URL = "https://github.com/InertExpert2911/Mutual_Fund_Data/raw/main"
CURATED_TOP_N = 15
```

## Testing

Google-style sizes. External boundaries: GitHub raw downloads (mocked), mfdata.in (mocked), LLM (mocked).

### Small tests (single process, deterministic)

**`test_data/test_store.py`**
- `test_schema_creation`: Create in-memory DuckDB, ensure schema creates all tables
- `test_refresh_log`: Insert a row, query it back

**`test_data/test_ingest.py`**
- `test_load_schemes_from_fixture`: Fixture CSV with 5 schemes → verify rows in `schemes` table
- `test_load_nav_history_from_fixture`: Fixture parquet with known NAV series → verify rows in `nav_history`
- `test_compute_returns_known_series`: Insert synthetic NAV series with known CAGR → verify `fund_returns` contains correct values (within 0.5% tolerance)
- `test_compute_returns_insufficient_history`: Fund with <1y history → NULL returns, doesn't crash
- `test_download_dataset`: Mock httpx, verify correct URLs hit and files written

**`test_data/test_universe.py`**
- `test_build_universe_top_n`: Synthetic data with 20 schemes in Large Cap → top 5 selected by returns
- `test_build_universe_multiple_categories`: Schemes across 3 categories → each gets its own top-N list
- `test_render_universe_context`: Populated universe → output contains all categories, fund names, returns
- `test_search_universe_category_filter`: Query with category → only matching funds returned

**`test_data/test_tools.py`** (update)
- `test_search_funds_universe_uses_duckdb`: Populated in-memory DuckDB → `search_funds_universe("Large Cap")` returns matching funds
- `test_get_fund_performance_still_works`: Mock mfdata.in → returns MutualFund (unchanged behaviour)

### Medium tests (cross-module, mocked externals)

**`test_integration.py`** (additions)
- `test_generate_plan_with_universe`: Populate test DuckDB + mock LLM → `generate_plan(include_universe=True)` injects universe into agent prompt (verify via captured prompt)
- `test_generate_plan_without_universe`: `include_universe=False` → no universe section in prompt

**`test_functional.py`** (additions)
- `test_data_refresh_help`: `subprime data refresh --help` runs
- `test_data_stats_empty`: With no DB, `subprime data stats` reports "No data"
- `test_data_stats_populated`: Pre-populated DB → command shows counts

### E2e tests (real APIs)

**`test_e2e.py`** (additions, marked `@pytest.mark.e2e`)
- `test_real_data_refresh_small_slice`: Run real download for a single scheme's slice (or use a tiny test branch if available), verify it lands in DuckDB. Skip if network unavailable.
- `test_advisor_uses_real_universe`: Run full advise flow with real DuckDB populated from real data, verify the plan references a fund from the universe.

## Non-Goals (out of scope for M2)

- Vector embeddings / semantic search
- Daily cron for auto-refresh (manual only)
- PDF export (moved to M2b or later)
- Fund-level fundamentals beyond what's in the CSV (launch date, AUM, category)
- Real-time universe refresh from mfdata.in detail enrichment (deferred — we use GitHub data as-is for curation)

## Migration / Backward Compatibility

- Existing `search_funds` tool is deprecated/removed and replaced with `search_funds_universe`. The advisor agent's tool list changes accordingly.
- `generate_plan` gains `include_universe=True` default. Tests using mocked `generate_plan` are unaffected; tests that exercise the real function need either a populated test DB or `include_universe=False`.
- CLI: no breaking changes to existing commands. `data` is a new sub-command group.
- If no DuckDB exists, advisor works without universe — graceful degradation. `subprime data refresh` is a one-time setup step for users.

## Rollout Plan

1. Build data layer (store + ingest + universe)
2. Write tests against small fixtures
3. Update advisor to optionally inject universe
4. Add CLI sub-commands
5. Run `subprime data refresh` on the deployment server
6. Rebuild Docker image (now uses `/app/data` volume for DuckDB)
7. Deploy, verify advisor uses universe

The Nomad job already has a host volume at `/opt/nomad/volumes/subprime_data` mounted to `/app/conversations`. Extend it to mount to `/app/data` as well (or add a second volume for the DuckDB file).
