# Operations

Runbook for things that live outside the codebase — third-party dashboards,
secrets, runtime behaviour. Keep this short; link to canonical sources
rather than duplicating their docs here.

## LLM provider routing (OpenRouter)

All advisor / judge / refine calls flow through OpenRouter
(`subprime.core.config.build_model` for the `openrouter:` prefix).
Provider preferences (fallbacks, quantization, sort order, ignored
providers, training-data policy) are configured **at the OpenRouter
account level**, not in code.

→ <https://openrouter.ai/settings/preferences>
→ Provider routing reference: <https://openrouter.ai/docs/features/provider-routing>

The settings we rely on:

- **Allow fallbacks: on** — if the preferred provider is degraded,
  OpenRouter falls through to the next.
- **Sort: throughput** (or "price-speed balance") — latency over the last
  5–10% of cost saving.
- **Quantization: allow FP8** — most multi-provider models (Mimo, several
  DeepSeek variants) only have FP8 endpoints; restricting blocks them all.
- **Training data: do not allow** — we send PII (CAS holdings, AIS
  totals); never want training samples.

When investigating "why did this model suddenly behave differently?",
check the dashboard before suspecting code.

### Per-request provider pinning

For cases where dashboard prefs aren't enough — e.g. pinning a specific
model to its first-party provider for cache stability — OpenRouter
accepts a `provider` object in the request body. Reference:
<https://openrouter.ai/docs/features/provider-routing>

```python
extra_body = {
    "provider": {
        "order": ["Xiaomi", "Novita"],
        "allow_fallbacks": True,
    },
}
```

**Backlog:** extend the `advisor_model` / `judge_model` flag values from
plain strings to JSON objects (e.g. `{"model": "openrouter:...", "provider": {...}}`)
so the per-request override is flag-driven rather than hardcoded in
`build_model`. Couple hours of work; not urgent until we hit a
provider-routing issue we can't fix at the dashboard level.

### Backlog: OpenRouter Presets

OpenRouter ships a "Presets" feature (<https://openrouter.ai/docs/guides/features/presets>,
managed at <https://openrouter.ai/settings/presets>) that bundles model +
provider routing + sampling params + system prompt under a named handle.
Referenced in API calls as `@preset/<name>` or `<model>@preset/<name>`.

When we get to it, the migration is small:

  1. Create presets in the dashboard for our common roles:
     - `advisor-fast`        — mimo-v2-flash, pin Xiaomi first-party, reasoning off
     - `advisor-quality`     — grok-4-fast, xAI direct, no fallback
     - `judge-balanced`      — gpt-4.1, throughput sort
     - `judge-strong`        — claude-sonnet-4.6, deny training
     - `experiment-cheap`    — mimo, FP8 only, low temperature
  2. Flag values change from `openrouter:xiaomi/mimo-v2-flash` to
     `openrouter:@preset/advisor-fast`.
  3. Verify `OpenAIChatModel` passes the `@preset/...` model string through
     unchanged (one smoke test).

Pros: provider pin + reasoning config + sampling params live in one named
handle, dashboard-versioned, swappable without code/flag changes.
Cons: presets themselves are dashboard-only — no CRUD API for them, so
provisioning isn't fully automated.

Skip until we have ≥4 distinct routing setups in flight. Today we have ~2
(mimo for live, gpt-4.1 for judge), so the indirection isn't paying yet.

## Feature flags

CRUD via `/api/v2/admin/flags/{key}` with a Bearer token
(`SUBPRIME_ADMIN_TOKEN`). Targeting attributes are documented in
`subprime.flags.context.flag_ctx`. Definition syntax follows GrowthBook's
JSON format; see <https://docs.growthbook.io/lib/python>.

```bash
ADMIN=$SUBPRIME_ADMIN_TOKEN
curl https://finadvisor.gkamal.online/api/v2/admin/flags -H "Authorization: Bearer $ADMIN"
```

## Email delivery (Resend)

OTP emails ride through `apps/web/email.py`. Backend preference:
Resend → SES → SMTP. Resend domain is `finadvisor.gkamal.online`,
DNS records (SPF, DKIM x2) live in Cloudflare for `gkamal.online`.

→ <https://resend.com/domains>
→ <https://resend.com/api-keys>

## Tempfile hygiene

`subprime.core.tempfiles.pdf_workspace` is the only blessed way to
write user-uploaded bytes to disk. It uses `delete=True` so the file
unlinks on context exit; a background scrubber (launched in the FastAPI
lifespan) sweeps `/tmp/subprime-*.pdf` every 5 min as a second line of
defence for crash paths.

## Per-session tracing

Every span we emit is tagged with `subprime.session_id` (see
`subprime.observability.attrs.SESSION_ID`). To investigate a slow / failed
session, copy the session id from the cookie or DB and search HyperDX:

  - **HyperDX**: filter `subprime.session_id = "<id>"` to see the full
    timeline (profile submit → strategy → plan stages → judge calls)
    with elapsed-time + token-usage attributes per span.
  - Common attributes: `subprime.advisor_model`, `subprime.refine_model`,
    `subprime.elapsed_s`, `subprime.input_tokens`, `subprime.output_tokens`,
    `subprime.cache_read_tokens`, `subprime.cache_hit_ratio`, `subprime.tier`.

For one-off debugging without HyperDX, container stderr also carries
`[plan <id8>] START | stage X persisted | DONE in Ns` log lines that are
greppable by the first 8 chars of the session id.

## Database / migrations

`feature_flags` table is created at startup by `subprime.flags.init_flags`
(idempotent CREATE TABLE IF NOT EXISTS). Other tables (sessions,
conversations, otps) were created manually or by a one-off Alembic run
before this system existed; `subprime data migrate` is **DuckDB only**
(fund universe), not Postgres.

If you add a new Postgres table, prefer self-creating it on the same
pattern as `feature_flags` rather than wiring Alembic into Nomad.

## Deploys

Blue-green via `scripts/blue-green-deploy.sh --auto-promote`. Smoke
suite is in `scripts/smoke.sh`. Caddy active-color file at
`/etc/caddy/active-finadvisor.caddy`.
