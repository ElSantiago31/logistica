-- ============================================================
--  CLEANUP: Eliminar evento de prueba 49325566 de producción
-- ============================================================
--  Ejecutar DESPUÉS de verificar que el fix funciona.
--  Elimina:
--    - event_assignments del evento de prueba
--    - event_coordinator_quotas del evento de prueba
--    - event_staff_needs del evento de prueba
--    - event_staff_assignments del evento de prueba
--    - El evento mismo
-- ============================================================

BEGIN;

-- 1) Eliminar asignaciones de operadores
DELETE FROM event_assignments
WHERE event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid;

-- 2) Eliminar cupos de coordinadores
DELETE FROM event_coordinator_quotas
WHERE event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid;

-- 3) Eliminar staff needs (cuotas por rol)
DELETE FROM event_staff_needs
WHERE event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid;

-- 4) Eliminar staff assignments (checkin/intendencia)
DELETE FROM event_staff_assignments
WHERE event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid;

-- 5) Eliminar audit logs
DELETE FROM event_audit_logs
WHERE event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid;

-- 6) Eliminar el evento mismo
DELETE FROM events
WHERE id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid;

COMMIT;

-- Verificar que quedó vacío
SELECT 'eventos_restantes' AS check, COUNT(*) AS valor
FROM events
WHERE id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid;