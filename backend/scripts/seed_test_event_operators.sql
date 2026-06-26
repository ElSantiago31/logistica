-- ============================================================
--  SEED: Asignar operadores de prueba al evento 49325566
-- ============================================================
--  Toma 5 operadores del evento FutbolFest CON su coordinador
--  original (programmed_by) para probar el flujo real.
-- ============================================================

BEGIN;

-- Insertar 5 asignaciones CON su coordinador original del FutbolFest
INSERT INTO event_assignments (
    id, event_id, operator_id, role_id, status,
    programmed_by, admitted_by,
    reminder_sent, confirmed_at,
    created_at, updated_at
)
SELECT
    gen_random_uuid(),
    '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid,
    ea.operator_id,
    ea.role_id,
    'confirmed',
    ea.programmed_by,   -- conserva el coordinador original
    ea.programmed_by,   -- admitted_by tambien (ya con backfill)
    false,              -- reminder_sent (NOT NULL, no tiene default a nivel DB)
    NOW(),              -- confirmed_at
    NOW(),
    NOW()
FROM event_assignments ea
WHERE ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND NOT EXISTS (
      SELECT 1 FROM event_assignments existing
      WHERE existing.event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid
        AND existing.operator_id = ea.operator_id
  )
LIMIT 5;

COMMIT;

-- ============================================================
--  VER LOS CC DE PRUEBA (document_number está en users, no en operators)
-- ============================================================
SELECT
    u.document_number,
    u.first_name || ' ' || u.last_name AS nombre,
    ea.status,
    ea.programmed_by,
    ea.admitted_by
FROM event_assignments ea
JOIN operators o ON o.id = ea.operator_id
JOIN users u ON u.id = o.user_id
WHERE ea.event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid
ORDER BY u.document_number;