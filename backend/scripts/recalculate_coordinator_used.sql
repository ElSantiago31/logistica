-- ============================================================
-- REPARACIÓN GLOBAL: cupos de coordinadores + quantity_confirmed
-- ============================================================
-- Problema histórico:
--   1. _count_used_by_coordinator contaba TODAS las asignaciones
--      (invited, rejected, no_show, cancelled, inactivas) lo que inflaba
--      el "used" de los cupos de coordinadores.
--   2. La importación por Excel creaba asignaciones con status='confirmed'
--      pero no actualizaba event_staff_needs.quantity_confirmed.
--
-- Este script recalcula AMBOS contadores desde la fuente de verdad
-- (asignaciones reales con status IN ('confirmed','checked_in') y activas).
-- Se ejecuta UNA sola vez en producción después del deploy del fix.
--
-- Uso (en el contenedor de postgres):
--   docker exec -i logistica_postgres psql -U logistica -d logistica \
--     < backend/scripts/recalculate_coordinator_used.sql
--
-- Es IDEMPOTENTE: se puede ejecutar varias veces sin riesgo.
-- ============================================================

BEGIN;

-- 1. Recalcular quantity_confirmed de TODOS los cargos (event_staff_needs).
--    Cuenta operadores confirmados/checked_in y activos por rol+evento.
UPDATE event_staff_needs esn
SET quantity_confirmed = sub.cnt
FROM (
    SELECT esn2.id AS need_id,
           COALESCE(count(a.id), 0) AS cnt
    FROM event_staff_needs esn2
    LEFT JOIN event_assignments a
        ON a.event_id = esn2.event_id
       AND a.role_id  = esn2.role_id
       AND a.status IN ('confirmed', 'checked_in')
       AND a.is_active = true
    GROUP BY esn2.id
) sub
WHERE esn.id = sub.need_id
  AND esn.quantity_confirmed IS DISTINCT FROM sub.cnt;

-- Nota: los "usados" del cupo de coordinador NO se persisten en una columna,
-- se calculan en runtime por _count_used_by_coordinator. Por lo tanto el fix
-- en backend/app/services/events.py (filtrar status+is_active) basta para que
-- la UI muestre el "used" correcto en todos los eventos sin necesidad de SQL.
-- Si en el futuro se agrega una columna event_coordinator_quotas.used_count,
-- este sería el UPDATE correspondiente:
--
-- UPDATE event_coordinator_quotas q
-- SET used_count = COALESCE(sub.cnt, 0)
-- FROM (
--     SELECT a.event_id, a.admitted_by_operator_id, count(*) AS cnt
--     FROM event_assignments a
--     WHERE a.status IN ('confirmed', 'checked_in')
--       AND a.is_active = true
--       AND a.admitted_by_operator_id IS NOT NULL
--     GROUP BY a.event_id, a.admitted_by_operator_id
-- ) sub
-- WHERE q.event_id = sub.event_id
--   AND q.coordinator_operator_id = sub.admitted_by_operator_id;

COMMIT;

-- Reporte de verificación (opcional, no afecta la transacción).
SELECT
    e.name     AS evento,
    u.first_name || ' ' || u.last_name AS coordinador,
    q.quota,
    COALESCE(c.used, 0) AS used_real,
    (q.quota - COALESCE(c.used, 0)) AS disponible
FROM event_coordinator_quotas q
JOIN events e    ON e.id = q.event_id
LEFT JOIN operators o ON o.id = q.coordinator_operator_id
LEFT JOIN users u     ON u.id = o.user_id
LEFT JOIN (
    SELECT a.event_id, a.admitted_by_operator_id, count(*) AS used
    FROM event_assignments a
    WHERE a.status IN ('confirmed', 'checked_in')
      AND a.is_active = true
      AND a.admitted_by_operator_id IS NOT NULL
    GROUP BY a.event_id, a.admitted_by_operator_id
) c ON c.event_id = q.event_id
   AND c.admitted_by_operator_id = q.coordinator_operator_id
ORDER BY e.name, coordinador;