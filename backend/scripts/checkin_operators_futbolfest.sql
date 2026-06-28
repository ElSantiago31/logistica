-- ============================================================
--  CHECK-IN FORZADO de 4 operadores en el evento FutbolFest
-- ============================================================
--  Evento : 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1
--  Cédulas:
--    1020733558
--    1019605672
--    1091357269
--    1069174857
--
--  PROBLEMA: Estos operadores tienen un registro en attendance_log
--  (de un intento previo de check-in), pero event_assignments.status
--  quedó en 'confirmed'. El endpoint de check-in responde 409
--  "Operador ya registrado" sin actualizar el status, creando un
--  deadlock (no se puede check-in de nuevo pero el status nunca
--  llega a 'checked_in').
--
--  FIX: Actualiza AMBAS tablas para que queden consistentes:
--    1. event_assignments.status -> 'checked_in'
--    2. attendance_log con INSERT ... ON CONFLICT DO NOTHING
--
--  (Respeta programmed_by/admitted_by existentes)
-- ============================================================
--  USO (en la VPS de producción):
--    docker exec -i logistica_postgres psql -U logistica -d logistica \
--      < backend/scripts/checkin_operators_futbolfest.sql
-- ============================================================

\set EVENT_ID '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'

BEGIN;

-- ------------------------------------------------------------
--  1) Estado ACTUAL de las 4 cédulas (assignment + attendance_log)
-- ------------------------------------------------------------
\echo '========== ESTADO ACTUAL =========='
SELECT
    u.document_number AS cedula,
    u.first_name || ' ' || u.last_name AS nombre,
    ea.status,
    ea.programmed_by,
    ea.admitted_by,
    CASE WHEN al.id IS NOT NULL THEN 'SI' ELSE 'NO' END AS tiene_attendance_log
FROM event_assignments ea
JOIN operators o ON o.id = ea.operator_id
JOIN users u ON u.id = o.user_id
LEFT JOIN attendance_log al ON al.event_id = ea.event_id
     AND al.operator_id = ea.operator_id
WHERE ea.event_id = :'EVENT_ID'::uuid
  AND u.document_number IN ('1020733558', '1019605672', '1091357269', '1069174857')
ORDER BY u.document_number;

-- ------------------------------------------------------------
--  2) Asegurar que attendance_log tenga los 4 registros
--     (ON CONFLICT DO NOTHING: si ya existe, no falla)
-- ------------------------------------------------------------
INSERT INTO attendance_log (id, event_id, operator_id, assignment_id, check_in_time, check_in_method, is_offline, created_at, updated_at)
SELECT
    gen_random_uuid(),
    ea.event_id,
    ea.operator_id,
    ea.id,
    NOW(),
    'manual',
    false,
    NOW(),
    NOW()
FROM event_assignments ea
JOIN operators o ON o.id = ea.operator_id
JOIN users u ON u.id = o.user_id
WHERE ea.event_id = :'EVENT_ID'::uuid
  AND u.document_number IN ('1020733558', '1019605672', '1091357269', '1069174857')
ON CONFLICT (event_id, operator_id) DO NOTHING;

-- ------------------------------------------------------------
--  3) HACER CHECK-IN (status -> 'checked_in')
-- ------------------------------------------------------------
UPDATE event_assignments ea
SET
    status        = 'checked_in',
    checked_in_at = NOW(),
    updated_at    = NOW()
FROM operators o
JOIN users u ON u.id = o.user_id
WHERE ea.operator_id = o.id
  AND ea.event_id    = :'EVENT_ID'::uuid
  AND u.document_number IN ('1020733558', '1019605672', '1091357269', '1069174857');

COMMIT;

-- ============================================================
--  4) VERIFICACIÓN FINAL
-- ============================================================
\echo ''
\echo '========== ESTADO DESPUÉS DEL CHECK-IN FORZADO =========='
SELECT
    u.document_number AS cedula,
    u.first_name || ' ' || u.last_name AS nombre,
    ea.status,
    ea.programmed_by,
    ea.admitted_by,
    ea.checked_in_at,
    CASE WHEN al.id IS NOT NULL THEN 'SI' ELSE 'NO' END AS tiene_attendance_log
FROM event_assignments ea
JOIN operators o ON o.id = ea.operator_id
JOIN users u ON u.id = o.user_id
LEFT JOIN attendance_log al ON al.event_id = ea.event_id
     AND al.operator_id = ea.operator_id
WHERE ea.event_id = :'EVENT_ID'::uuid
  AND u.document_number IN ('1020733558', '1019605672', '1091357269', '1069174857')
ORDER BY u.document_number;

-- ------------------------------------------------------------
--  5) Reporte de cédulas NO encontradas
-- ------------------------------------------------------------
\echo ''
\echo '========== CÉDULAS NO ENCONTRADAS EN EL EVENTO (si alguna) =========='
SELECT v.cedula AS cedula_no_encontrada
FROM (VALUES ('1020733558'), ('1019605672'), ('1091357269'), ('1069174857')) AS v(cedula)
WHERE NOT EXISTS (
    SELECT 1
    FROM event_assignments ea
    JOIN operators o ON o.id = ea.operator_id
    JOIN users u ON u.id = o.user_id
    WHERE ea.event_id = :'EVENT_ID'::uuid
      AND u.document_number = v.cedula
);

-- ------------------------------------------------------------
--  6) Conteo total del evento por estado
-- ------------------------------------------------------------
\echo ''
\echo '========== CONTEO POR ESTADO (evento) =========='
SELECT
    status,
    COUNT(*) AS total
FROM event_assignments
WHERE event_id = :'EVENT_ID'::uuid
GROUP BY status
ORDER BY status;
