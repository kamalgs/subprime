-- Trend metrics for the admin Metabase dashboard.
--
-- Each block is one Saved Question / dashboard panel. Queries are
-- written to run as the read-only `metabase_ro` role: SELECT only, no
-- mutation, no temp tables, no functions outside the standard library.
--
-- Verify a query manually:
--   docker exec <pg-container> psql -U finadvisor -d finadvisor -f trends.sql
--
-- Metabase will execute these via its native query interface; the
-- text here is the source of truth — when a panel SQL changes, edit
-- both this file and re-export the dashboard JSON.


-- ── 1. New conversations per day (last 30 days) ──────────────────────
-- Panel: "Daily conversations". Bar chart, x = day, y = count.
SELECT
    date_trunc('day', created_at)::date AS day,
    count(*)                            AS conversations
FROM conversations
WHERE created_at >= now() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;


-- ── 2. New conversations per week (last 12 weeks) ────────────────────
-- Panel: "Weekly conversations". Bar chart.
SELECT
    date_trunc('week', created_at)::date AS week,
    count(*)                             AS conversations
FROM conversations
WHERE created_at >= now() - INTERVAL '12 weeks'
GROUP BY 1
ORDER BY 1;


-- ── 3. New conversations per month (last 12 months) ──────────────────
-- Panel: "Monthly conversations". Bar chart.
SELECT
    date_trunc('month', created_at)::date AS month,
    count(*)                              AS conversations
FROM conversations
WHERE created_at >= now() - INTERVAL '12 months'
GROUP BY 1
ORDER BY 1;


-- ── 4. Daily split: basic vs premium ─────────────────────────────────
-- Panel: "Mode mix (daily)". Stacked bar chart, x = day, y = count, series = mode.
SELECT
    date_trunc('day', created_at)::date AS day,
    mode,
    count(*)                            AS conversations
FROM conversations
WHERE created_at >= now() - INTERVAL '30 days'
GROUP BY 1, 2
ORDER BY 1, 2;


-- ── 5. Plan-completion rate (rolling 7-day window) ───────────────────
-- Panel: "Plan completion %". Line chart, x = day, y = pct.
-- A conversation "completed" the plan stage when `plan` is non-null.
SELECT
    date_trunc('day', created_at)::date                          AS day,
    count(*)                                                     AS started,
    count(*) FILTER (WHERE plan IS NOT NULL)                     AS completed,
    round(
        100.0 * count(*) FILTER (WHERE plan IS NOT NULL) / count(*),
        1
    )                                                            AS completion_pct
FROM conversations
WHERE created_at >= now() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;


-- ── 6. Persona mix (last 30 days) ────────────────────────────────────
-- Panel: "Persona usage". Pie / donut chart.
-- Persona IDs are stored under profile->>'persona_id' for premium-tier
-- demo flows; null in basic / non-demo conversations.
SELECT
    coalesce(profile->>'persona_id', '(no persona)') AS persona,
    count(*)                                          AS conversations
FROM conversations
WHERE created_at >= now() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 2 DESC;


-- ── 7. Strategy-chat depth distribution ──────────────────────────────
-- Panel: "Strategy revisions". Histogram, x = revision count, y = freq.
-- Each entry in strategy_chat is one user-assistant exchange about the
-- proposed strategy; deeper chats = more revision before approval.
SELECT
    coalesce(jsonb_array_length(strategy_chat), 0) AS revisions,
    count(*)                                       AS conversations
FROM conversations
WHERE created_at >= now() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;


-- ── 8. Headline counters (no time series) ────────────────────────────
-- Panels: "Total conversations", "Last 7 days", "Last 24 hours".
-- One row, several columns; Metabase will split into separate scalar
-- panels via column-picker.
SELECT
    count(*)                                                              AS total,
    count(*) FILTER (WHERE created_at >= now() - INTERVAL '7 days')       AS last_7d,
    count(*) FILTER (WHERE created_at >= now() - INTERVAL '24 hours')     AS last_24h,
    count(*) FILTER (WHERE plan IS NOT NULL)                              AS plans_completed
FROM conversations;
