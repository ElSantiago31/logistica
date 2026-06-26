-- ============================================================
--  FIX: Limpiar y regenerar operadores de prueba del evento 49325566
-- ============================================================
--  Problema: hay 13 operadores con programmed_by=NULL (de runs
--  anteriores del script viejo). Este script:
--    1. DELETE todo del evento de prueba
--    2. Re-inserta 5 operadores CON programmed_by del FutbolFest
--    3. Muestra el resultado
-- ============================================================

BEGIN;

-- 1) Limpiar TODAS las asignaciones del evento de prueba
DELETE FROM event_assignments
WHERE event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid;

-- 2) Re-insertar 5 operadores CON su coordinador original del FutbolFest
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
    ea.programmed_by,
    ea.programmed_by,
    false,
    NOW(),
    NOW(),
    NOW()
FROM event_assignments ea
WHERE ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND ea.programmed_by IS NOT NULL
LIMIT 5;

COMMIT;

-- 3) Verificar
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