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
