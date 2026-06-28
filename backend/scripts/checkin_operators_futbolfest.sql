-- ============================================================
--  CHECK-IN de 4 operadores en el evento FutbolFest
-- ============================================================
--  Evento : 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1
--  Cédulas:
--    1020733558
--    1019605672
--    1091357269
--    1069174857
--  Cambio: status -> 'checked_in', checked_in_at = NOW()
--  (Respeta programmed_by/admitted_by existentes)
-- ============================================================
--  USO (en la VPS de producción):
--    docker exec -i logistica_postgres psql -U logistica -d logistica \
--      < backend/scripts/checkin_operators_futbolfest.sql
-- ============================================================

\set EVENT_ID '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'

BEGIN;

-- ------------------------------------------------------------
--  1) Estado ACTUAL de las 4 cédulas
-- ------------------------------------------------------------
\echo '========== ESTADO ACTUAL =========='
SELECT
    u.document_number AS cedula,
    u.first_name || ' ' || u.last_name AS nombre,
    ea.status,
    ea.programmed_by,
    ea.admitted_by
FROM event_assignments ea
JOIN operators o ON o.id = ea.operator_id
JOIN users u ON u.id = o.user_id
WHERE ea.event_id = :'EVENT_ID'::uuid
  AND u.document_number IN ('1020733558', '1019605672', '1091357269', '1069174857')
ORDER BY u.document_number;

-- ------------------------------------------------------------
--  2) HACER CHECK-IN (status -> 'checked_in')
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
--  3) VERIFICACIÓN FINAL
-- ============================================================
\echo ''
\echo '========== ESTADO DESPUÉS DEL CHECK-IN =========='
SELECT
    u.document_number AS cedula,
    u.first_name || ' ' || u.last_name AS nombre,
    ea.status,
    ea.programmed_by,
    ea.admitted_by,
    ea.checked_in_at
FROM event_assignments ea
JOIN operators o ON o.id = ea.operator_id
JOIN users u ON u.id = o.user_id
WHERE ea.event_id = :'EVENT_ID'::uuid
  AND u.document_number IN ('1020733558', '1019605672', '1091357269', '1069174857')
ORDER BY u.document_number;

-- ------------------------------------------------------------
--  4) Reporte de cédulas NO encontradas
-- ------------------------------------------------------------
\echo ''
\echo '========== CÉDULAS NO ENCONTRADAS (si alguna) =========='
SELECT u.document_number AS cedula_no_encontrada
FROM (VALUES ('1020733558'), ('1019605672'), ('1091357269'), ('1069174857')) AS v(cedula)
LEFT JOIN users u ON u.document_number = v.cedula
WHERE u.document_number IS NULL;

-- ------------------------------------------------------------
--  5) Conteo total del evento por estado
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