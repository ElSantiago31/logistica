-- ============================================================
-- REPARACIÓN GLOBAL: cupos de coordinadores + quantity_confirmed
-- ============================================================
-- Problemas históricos:
--   1. _count_used_by_coordinator contaba TODAS las asignaciones
--      (invited, rejected, no_show, cancelled, inactivas) lo que inflaba
--      el "used" de los cupos de coordinadores.
--   2. La importación por Excel creaba asignaciones con status='confirmed'
--      pero no actualizaba event_staff_needs.quantity_confirmed.
--   3. _ensure_coordinator_quotas creaba quotas con quota = count + 5
--      (margen arbitrario) y no actualizaba las quotas existentes al
--      reimportar, dejando cupos inflados (ej: 21 cuando debía ser 16).
--
-- Este script recalcula TODOS los contadores desde la fuente de verdad
-- (asignaciones reales con status IN ('confirmed','checked_in') y activas):
--   - quantity_confirmed de event_staff_needs (cargos de personal).
--   - quota de event_coordinator_quotas (cupos de coordinadores).
--
-- Se ejecuta UNA sola vez en producción después del deploy del fix.
-- Es IDEMPOTENTE: se puede ejecutar varias veces sin riesgo.
--
-- Uso (en el contenedor de postgres):
--   docker exec -i logistica_postgres psql -U logistica -d logistica \
--     < backend/scripts/recalculate_coordinator_used.sql
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

-- 2. Recalcular quota de TODOS los cupos de coordinadores
--    (event_coordinator_quotas) desde las asignaciones confirmadas.
--    El cupo real = número de operadores confirmados/checked_in que este
--    coordinador tiene asignados en el evento.
--    Esto repara el drift de quotas infladas por count + 5.
--
--    IMPORTANTE: esto deja quota = used_real (sin margen). Si querés
--    conservar un margen para permitir invitaciones pendientes, sumá un
--    offset (ej: + 0 para no inflar). Aquí usamos 0 porque el "usado"
--    ya representa la realidad del evento.
UPDATE event_coordinator_quotas q
SET quota = COALESCE(sub.cnt, q.quota)
FROM (
    SELECT a.event_id,
           COALESCE(a.admitted_by_operator_id, NULL) AS coord_op_id,
           a.admitted_by,
           count(*) AS cnt
    FROM event_assignments a
    WHERE a.status IN ('confirmed', 'checked_in')
      AND a.is_active = true
    GROUP BY a.event_id, a.admitted_by_operator_id, a.admitted_by
) sub
WHERE q.event_id = sub.event_id
  AND (
      -- Match por FK de operador coordinador (flujo nuevo)
      (q.coordinator_operator_id IS NOT NULL
          AND q.coordinator_operator_id = sub.coord_op_id)
      OR
      -- Match por nombre legacy (coordinador texto libre)
      (q.coordinator_operator_id IS NULL
          AND q.coordinator ILIKE sub.admitted_by)
  )
  AND q.quota IS DISTINCT FROM COALESCE(sub.cnt, q.quota);

COMMIT;

-- ============================================================
-- Reporte de verificación (no afecta la transacción).
-- ============================================================
SELECT
    e.name     AS evento,
    COALESCE(u.first_name || ' ' || u.last_name, q.coordinator) AS coordinador,
    q.quota                                 AS cupo,
    COALESCE(c.used, 0)                     AS usados_real,
    (q.quota - COALESCE(c.used, 0))         AS disponible
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