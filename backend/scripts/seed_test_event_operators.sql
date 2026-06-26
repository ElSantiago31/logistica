-- ============================================================
--  SEED: Asignar operadores de prueba al evento 49325566
-- ============================================================
--  Toma 5 operadores del evento FutbolFest y los asigna al
--  evento de prueba (sin programmed_by, para probar el selector)
-- ============================================================

BEGIN;

-- Insertar 5 asignaciones SIN coordinador (para probar el fix del selector)
INSERT INTO event_assignments (id, event_id, operator_id, role_id, status, programmed_by, admitted_by, created_at, updated_at)
SELECT
    gen_random_uuid(),
    '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid,
    o.id,
    ea.role_id,
    'confirmed',
    NULL,   -- sin coordinador para probar el selector
    NULL,
    NOW(),
    NOW()
FROM event_assignments ea
JOIN operators o ON o.id = ea.operator_id
WHERE ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND NOT EXISTS (
      SELECT 1 FROM event_assignments existing
      WHERE existing.event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid
        AND existing.operator_id = ea.operator_id
  )
LIMIT 5;

COMMIT;

-- ============================================================
--  VER LOS CC DE PRUEBA
-- ============================================================
SELECT
    o.document_number,
    o.first_name || ' ' || o.last_name AS nombre,
    ea.status,
    ea.programmed_by
FROM event_assignments ea
JOIN operators o ON o.id = ea.operator_id
WHERE ea.event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid
ORDER BY o.document_number;