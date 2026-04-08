# ADR 004: mfdata.in as Primary Data Source

## Status

Accepted

## Context

The advisor agent needs real mutual fund data (NAV, expense ratio, AUM, categories, fund house) to generate grounded investment plans. Options considered:

1. **mfdata.in API** -- free REST API for Indian mutual fund data. No auth required. Covers AMFI-registered schemes with current NAV, basic metadata.
2. **AMFI website scraping** -- official source but no API, brittle scraping.
3. **MFApi.in** -- another free API, similar coverage.
4. **InertExpert2911/Mutual_Fund_Data** (GitHub) -- CSV dataset with historical data, returns, risk grades. Static, not live.
5. **Commercial APIs** (Morningstar, Value Research) -- comprehensive but paid.

## Decision

Use mfdata.in as the primary live data source. The `MFDataClient` wraps it with async httpx. PydanticAI tools (`search_funds`, `get_fund_performance`, `compare_funds`) provide the agent-facing interface.

The InertExpert2911/Mutual_Fund_Data GitHub dataset is planned as a supplementary offline source (M2) for historical returns, risk grades, and Morningstar ratings not available from mfdata.in.

## Consequences

- **Positive**: Free, no API key needed, sufficient metadata for plan generation.
- **Positive**: Live data means plans reference real, current funds.
- **Negative**: Rate limits and availability are undocumented. Experiment runs with many tool calls may hit throttling. Mitigated by capping search results to 10 and potential future caching.
- **Negative**: Missing fields: historical returns (1y/3y/5y), risk grades, and reliable Morningstar ratings are sparse. Mitigated by the planned GitHub dataset integration in M2.
- **Negative**: External dependency -- if mfdata.in goes down, plan generation fails. Mitigated by respx mocking in tests.
