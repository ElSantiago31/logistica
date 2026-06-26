-- ============================================================
--  SEED: Preparar prueba del modal de reasignación
-- ============================================================
--  Estrategia:
--    1. Bajar el cupo de XIMENA H a 1 (temporal)
--    2. Agregar 2 operadores MÁS de XIMENA H (además del actual)
--    3. Así podemos:
--       - Check-in #1 (XIMENA H) → llena el cupo 1/1
--       - Check-in #2 (XIMENA H) → debe salir modal "Cupo lleno"
-- ============================================================

BEGIN;

-- 1) Bajar cupo de XIMENA H a 1 (solo para esta prueba)
UPDATE event_coordinator_quotas
SET quota = 1, updated_at = NOW()
WHERE event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid
  AND coordinator = 'XIMENA H';

-- 2) Agregar 2 operadores MÁS de XIMENA H del FutbolFest
--    (excluyendo los que ya están asignados al evento de prueba)
INSERT INTO event_assignments (
    id, event_id, operator_id, role_id, status,
    programmed_by, admitted_by,
    reminder_sent, confirmed_at, is_active,
    created_at, updated_at
)
SELECT
    gen_random_uuid(),
    '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid,
    ea.operator_id,
    ea.role_id,
    'confirmed',
    ea.programmed_by,
    ea.programmed_by,
    false,
    NOW(),
    true,
    NOW(),
    NOW()
FROM event_assignments ea
WHERE ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND ea.programmed_by = 'XIMENA H'
  AND ea.operator_id NOT IN (
      SELECT operator_id FROM event_assignments
      WHERE event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid
  )
LIMIT 2;

COMMIT;

-- 3) Verificar el estado de la prueba
SELECT
    'CUPOS_XIMENA' AS check,
    coordinator || ': ' || quota AS valor
FROM event_coordinator_quotas
WHERE event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid
  AND coordinator = 'XIMENA H'
UNION ALL
SELECT
    'OPERADORES_XIMENA',
    COUNT(*) || ' operadores de XIMENA H'
FROM event_assignments
WHERE event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid
  AND programmed_by = 'XIMENA H';