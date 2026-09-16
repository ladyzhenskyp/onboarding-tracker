-- =============================================================================
-- Time in stage.
--   Part A: every client's current stage and how long it has been there.
--   Part B: average days spent in each *completed* stage across all clients —
--           the dashboard's "average time-in-stage" metric.
-- Dialect: PostgreSQL. Parameter :now TIMESTAMP (e.g. NOW()).
-- =============================================================================

-- A. current stage per client, longest-running first
SELECT c.id,
       c.name,
       s.name                                              AS stage,
       h.entered_at,
       EXTRACT(DAY FROM (:now::timestamp - h.entered_at))::int AS days_in_stage
FROM clients c
JOIN client_stage_history h ON h.client_id = c.id AND h.exited_at IS NULL
JOIN stages s               ON s.id = h.stage_id
ORDER BY days_in_stage DESC;

-- B. average duration of completed stage visits, in pipeline order
SELECT s.name                                                                  AS stage,
       COUNT(*)                                                                AS completed_visits,
       ROUND(AVG(EXTRACT(EPOCH FROM (h.exited_at - h.entered_at)) / 86400.0), 1) AS avg_days,
       ROUND(MAX(EXTRACT(EPOCH FROM (h.exited_at - h.entered_at)) / 86400.0), 1) AS max_days
FROM client_stage_history h
JOIN stages s ON s.id = h.stage_id
WHERE h.exited_at IS NOT NULL
GROUP BY s.name, s.sort_order
ORDER BY s.sort_order;
