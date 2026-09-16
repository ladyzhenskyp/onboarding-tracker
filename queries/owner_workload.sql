-- =============================================================================
-- Workload per account owner: how many accounts, how many not yet live,
-- how many carry an open high/critical blocker, and total contract value.
-- (The full red/amber/green count per owner comes from at_risk_accounts.sql
-- grouped by owner; this query is the cheap version that needs no thresholds.)
-- Dialect: PostgreSQL. No parameters.
-- =============================================================================
SELECT u.id,
       u.name                                                         AS owner,
       u.role,
       COUNT(c.id)                                                    AS accounts,
       COUNT(c.id) FILTER (WHERE s.key <> 'live')                     AS onboarding,
       COUNT(DISTINCT b.client_id)                                    AS accounts_with_severe_blocker,
       COALESCE(SUM(c.contract_value), 0)                             AS contract_value
FROM users u
LEFT JOIN clients c  ON c.owner_id = u.id
LEFT JOIN stages s   ON s.id = c.current_stage_id
LEFT JOIN blockers b ON b.client_id = c.id
                    AND b.resolved_at IS NULL
                    AND b.severity IN ('high', 'critical')
WHERE u.is_active
GROUP BY u.id, u.name, u.role
ORDER BY accounts DESC, owner;
