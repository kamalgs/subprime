-- Source-of-truth SQL for the `conversations` Metabase Model.
--
-- This Model abstracts the JSONB columns (profile, strategy, plan,
-- strategy_chat) on the live `conversations` table into typed columns,
-- with proper Metabase semantic types so the GUI gets bucketing /
-- grouping right. Every saved question, metric, and dashboard panel
-- queries this Model rather than the raw table — schema changes in
-- the JSONB shape localise to this file instead of breaking every
-- dashboard.
--
-- The full Model definition (column types, semantic types, etc.)
-- lives alongside the SQL in `trends.metabase.json` under `model`.
-- When editing, keep both in sync.

SELECT
    id,
    session_id,
    investor_name,
    mode,
    created_at,
    (profile->>'age')::int                                  AS age,
    profile->>'persona_id'                                   AS persona_id,
    profile->>'risk_appetite'                                AS risk_appetite,
    (profile->>'investment_horizon_years')::int              AS investment_horizon_years,
    (profile->>'monthly_investible_surplus_inr')::numeric    AS monthly_surplus_inr,
    (profile->>'existing_corpus_inr')::numeric               AS existing_corpus_inr,
    profile->>'life_stage'                                   AS life_stage,
    profile->>'tax_bracket'                                  AS tax_bracket,
    plan IS NOT NULL                                         AS plan_completed,
    coalesce(jsonb_array_length(strategy_chat), 0)           AS revision_count
FROM conversations;
