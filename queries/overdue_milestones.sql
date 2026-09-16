-- =============================================================================
-- Open milestones past their due date, most overdue first.
-- "Overdue" is derived (status <> 'done' AND due_date < today), never stored.
-- Dialect: PostgreSQL. Parameter :today DATE (e.g. CURRENT_DATE).
-- Uses the partial index ix_milestones_open_due.
-- =============================================================================
SELECT m.id,
       c.name                              AS client,
       m.title,
       m.due_date,
       (:today::date - m.due_date)         AS days_overdue,
       m.status,
       u.name                              AS owner
FROM milestones m
JOIN clients c     ON c.id = m.client_id
LEFT JOIN users u  ON u.id = m.owner_id
WHERE m.status <> 'done'
  AND m.due_date < :today::date
ORDER BY days_overdue DESC, c.name;
