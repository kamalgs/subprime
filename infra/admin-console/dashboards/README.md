# Admin dashboards

Metabase dashboards for the internal admin console at
`admin.finadvisor.gkamal.online`.

The deploy lives in `~/projects/nomad` (Caddy site block, oauth2-proxy,
Metabase Nomad job, read-only Postgres role). This directory holds only
the read-side artefacts: the SQL behind each panel and the dashboard
JSON exports.

## Files

- `conversations.model.sql` — source-of-truth SQL for the `conversations`
  Metabase Model. Flattens the JSONB columns (`profile`, `strategy`,
  `plan`, `strategy_chat`) into typed columns. **Every saved question,
  metric, and dashboard panel queries this Model, not the raw table** —
  schema changes in the JSONB localise to this one file.
- `trends.sql` — historical SQL written before the Model existed. Each
  block was the source for one panel using raw `conversations`. Now
  superseded by the Model + the panels in `trends.metabase.json`. Kept
  for reference / standalone runs via `psql -f trends.sql`.
- `trends.metabase.json` — portable export of the Model + 5 Metrics +
  12 dashboard cards + grid layout. Intentionally *not* Metabase's
  native serialization (verbose, version-coupled, noisy diffs). The
  format here is "the inputs to a re-import script". When the Model
  SQL changes, edit `conversations.model.sql` AND re-export
  `trends.metabase.json` so the two stay in sync.

## Trends dashboard

The first dashboard. Twelve panels across four rows:

| #  | Panel                       | Type           | Window     |
|----|-----------------------------|----------------|------------|
| 1  | Daily conversations         | Bar            | 30 days    |
| 2  | Weekly conversations        | Bar            | 12 weeks   |
| 3  | Monthly conversations       | Bar            | 12 months  |
| 4  | Mode mix (daily)            | Stacked bar    | 30 days    |
| 5  | Plan completion %           | Line           | 30 days    |
| 6  | Persona mix                 | Donut          | 30 days    |
| 7  | Strategy revisions          | Histogram      | 30 days    |
| 8  | Headline counters           | Scalar (×4)    | all-time   |
| 9  | NPS (current)               | Scalar         | 30 days    |
| 10 | Feedback completion %       | Scalar         | all-time   |
| 11 | NPS over time (weekly)      | Line           | 12 weeks   |
| 12 | Recent feedback (free text) | Table (50 rows)| all-time   |

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
