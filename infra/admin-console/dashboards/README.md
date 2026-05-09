# Admin dashboards

Metabase dashboards for the internal admin console at
`admin.finadvisor.gkamal.online`.

The deploy lives in `~/projects/nomad` (Caddy site block, oauth2-proxy,
Metabase Nomad job, read-only Postgres role). This directory holds only
the read-side artefacts: the SQL behind each panel and the dashboard
JSON exports.

## Files

- `trends.sql` — source-of-truth SQL for every dashboard panel. Each
  block maps 1:1 to one Saved Question in Metabase. Standalone-runnable
  via `psql -f trends.sql`.
- `trends.metabase.json` — portable dashboard export. Records each card
  (name, display type, native SQL) plus the grid layout. Intentionally
  *not* Metabase's native serialization format — that's verbose,
  version-coupled, and produces noisy diffs even for trivial query
  edits. The format here is "the inputs to a re-import script".

## Trends dashboard

The first dashboard. Eight panels:

| # | Panel                  | Type           | Window     |
|---|------------------------|----------------|------------|
| 1 | Daily conversations    | Bar            | 30 days    |
| 2 | Weekly conversations   | Bar            | 12 weeks   |
| 3 | Monthly conversations  | Bar            | 12 months  |
| 4 | Mode mix (daily)       | Stacked bar    | 30 days    |
| 5 | Plan completion %      | Line           | 30 days    |
| 6 | Persona mix            | Donut          | 30 days    |
| 7 | Strategy revisions     | Histogram      | 30 days    |
| 8 | Headline counters      | Scalar (×4)    | all-time   |

When a panel's SQL changes, edit `trends.sql` *and* re-export
`trends.metabase.json` so the two stay in sync.

## Importing on a fresh Metabase instance

1. Bring up Metabase via the Nomad job (see `~/projects/nomad`).
2. Sign in as the admin user, add the `finadvisor` Postgres connection
   using the `metabase_ro` credentials.
3. Settings → Admin → Serialization → Import → upload
   `trends.metabase.json`. (Or via CLI: `java -jar metabase.jar import`.)
4. Verify each panel renders without an error against the connected DB.

## Why SQL-as-code alongside the JSON export

Metabase's serialisation format is verbose and reorders fields in ways
that produce noisy diffs even for trivial query edits. Keeping the raw
SQL in `trends.sql` gives a small reviewable artefact: PR diffs on the
SQL file are signal, the JSON re-export is mechanical follow-up.
