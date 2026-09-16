-- =============================================================================
-- At-risk accounts: one row per client with the colour the rules produce and
-- a semicolon-separated list of reasons. Mirrors app/services/risk.py.
--
-- Dialect: PostgreSQL. Parameters (bind from the app or replace by hand):
--   :today                DATE      e.g. CURRENT_DATE
--   :now                  TIMESTAMP e.g. NOW()
--   :high_blocker_days    INT       default 7
--   :overdue_threshold    INT       default 2
--   :go_live_warning_days INT       default 14
-- Stage thresholds are inlined in the CASE below (kickoff 10, discovery 30,
-- uat 21, prod 14) to keep this file self-contained.
-- =============================================================================
WITH current_stage AS (
    -- the open stage-history row = the client's current stage
    SELECT h.client_id,
           s.key   AS stage_key,
           s.name  AS stage_name,
           (:now::timestamp - h.entered_at) AS time_in_stage
    FROM client_stage_history h
    JOIN stages s ON s.id = h.stage_id
    WHERE h.exited_at IS NULL
),
open_blockers AS (
    SELECT client_id,
           COUNT(*) FILTER (WHERE severity = 'critical')                                  AS critical_open,
           COUNT(*) FILTER (WHERE severity = 'high'
                              AND opened_at < :now::timestamp - make_interval(days => :high_blocker_days)) AS high_stale,
           STRING_AGG(title, '; ' ORDER BY opened_at)
               FILTER (WHERE severity = 'critical'
                          OR (severity = 'high'
                              AND opened_at < :now::timestamp - make_interval(days => :high_blocker_days))) AS blocker_titles
    FROM blockers
    WHERE resolved_at IS NULL
    GROUP BY client_id
),
overdue AS (
    SELECT client_id, COUNT(*) AS overdue_milestones
    FROM milestones
    WHERE status <> 'done' AND due_date < :today::date
    GROUP BY client_id
),
scored AS (
    SELECT c.id,
           c.name,
           c.segment,
           u.name                                            AS owner,
           cs.stage_key,
           cs.stage_name,
           EXTRACT(DAY FROM cs.time_in_stage)::int           AS days_in_stage,
           (c.target_go_live_date - :today::date)            AS days_to_go_live,
           COALESCE(ob.critical_open, 0)                     AS critical_open,
           COALESCE(ob.high_stale, 0)                        AS high_stale,
           ob.blocker_titles,
           COALESCE(od.overdue_milestones, 0)                AS overdue_milestones,
           CASE cs.stage_key
               WHEN 'kickoff'   THEN 10
               WHEN 'discovery' THEN 30
               WHEN 'uat'       THEN 21
               WHEN 'prod'      THEN 14
           END                                               AS stage_max_days,
           cs.stage_key IN ('prod', 'live')                  AS in_safe_stage
    FROM clients c
    JOIN users u          ON u.id = c.owner_id
    JOIN current_stage cs ON cs.client_id = c.id
    LEFT JOIN open_blockers ob ON ob.client_id = c.id
    LEFT JOIN overdue od       ON od.client_id = c.id
)
SELECT id,
       name,
       segment,
       owner,
       stage_name,
       days_in_stage,
       days_to_go_live,
       CASE
           WHEN critical_open > 0 OR high_stale > 0
                OR (NOT in_safe_stage AND days_to_go_live < 0)                          THEN 'red'
           WHEN overdue_milestones >= :overdue_threshold
                OR (NOT in_safe_stage AND days_to_go_live BETWEEN 0 AND :go_live_warning_days)
                OR (stage_max_days IS NOT NULL AND days_in_stage > stage_max_days)      THEN 'amber'
           ELSE 'green'
       END AS health,
       CONCAT_WS('; ',
           CASE WHEN critical_open > 0 THEN 'open critical blocker' END,
           CASE WHEN high_stale > 0    THEN 'high blocker open > ' || :high_blocker_days || ' days' END,
           CASE WHEN NOT in_safe_stage AND days_to_go_live < 0
                THEN 'go-live missed by ' || -days_to_go_live || ' days' END,
           CASE WHEN overdue_milestones >= :overdue_threshold
                THEN overdue_milestones || ' overdue milestones' END,
           CASE WHEN NOT in_safe_stage AND days_to_go_live BETWEEN 0 AND :go_live_warning_days
                THEN 'go-live in ' || days_to_go_live || ' days, still in ' || stage_name END,
           CASE WHEN stage_max_days IS NOT NULL AND days_in_stage > stage_max_days
                THEN days_in_stage || ' days in ' || stage_name || ' (max ' || stage_max_days || ')' END
       ) AS reasons,
       blocker_titles
FROM scored
ORDER BY CASE
             WHEN critical_open > 0 OR high_stale > 0 OR (NOT in_safe_stage AND days_to_go_live < 0) THEN 0
             WHEN overdue_milestones >= :overdue_threshold
                  OR (NOT in_safe_stage AND days_to_go_live BETWEEN 0 AND :go_live_warning_days)
                  OR (stage_max_days IS NOT NULL AND days_in_stage > stage_max_days) THEN 1
             ELSE 2
         END,
         days_to_go_live;
