-- ============================================================
--  CAMBIAR STATUS del operador 1013642667 de 'rejected' a 'confirmed'
-- ============================================================
--  Cédula operador : 1013642667
--  Evento          : 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1 (Claro FutbolFest)
--  Coordinador     : CLAUDIA B
--  Cambio          : rejected -> confirmed
-- ============================================================
--  USO (en la VPS de producción):
--    docker exec -i logistica_postgres psql -U logistica -d logistica \
--      < backend/scripts/fix_operator_status.sql
-- ============================================================

\set EVENT_ID '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'
\set CEDULA   '1013642667'
\set COORD    'CLAUDIA B'

BEGIN;

-- ------------------------------------------------------------
--  1) Mostrar el estado ACTUAL (antes del cambio)
-- ------------------------------------------------------------
\echo '========== ESTADO ACTUAL =========='
SELECT
    u.document_number AS cedula,
    u.first_name || ' ' || u.last_name AS nombre,
    ea.status,
    ea.programmed_by,
    ea.admitted_by,
    ea.rejected_at
FROM event_assignments ea
JOIN operators o ON o.id = ea.operator_id
JOIN users u ON u.id = o.user_id
WHERE ea.event_id = :'EVENT_ID'::uuid
  AND u.document_number = :'CEDULA';

-- ------------------------------------------------------------
--  2) ACTUALIZAR status a 'confirmed' y limpiar rejected_at
-- ------------------------------------------------------------
UPDATE event_assignments ea
SET
    status       = 'confirmed',
    programmed_by = :'COORD',
    admitted_by   = :'COORD',
    confirmed_at = COALESCE(ea.confirmed_at, NOW()),
    rejected_at  = NULL,
    updated_at   = NOW()
FROM operators o
JOIN users u ON u.id = o.user_id
WHERE ea.operator_id = o.id
  AND ea.event_id    = :'EVENT_ID'::uuid
  AND u.document_number = :'CEDULA';

COMMIT;

-- ============================================================
--  3) VERIFICACIÓN FINAL
-- ============================================================
\echo ''
\echo '========== ESTADO DESPUÉS DEL CAMBIO =========='
SELECT
    u.document_number AS cedula,
    u.first_name || ' ' || u.last_name AS nombre,
    ea.status,
    ea.programmed_by,
    ea.admitted_by,
    ea.confirmed_at,
    ea.rejected_at
FROM event_assignments ea
JOIN operators o ON o.id = ea.operator_id
JOIN users u ON u.id = o.user_id
WHERE ea.event_id = :'EVENT_ID'::uuid
  AND u.document_number = :'CEDULA';

-- Conteo total del evento por coordinador
\echo ''
\echo '========== CONTEO POR COORDINADOR (evento) =========='
SELECT
    COALESCE(admitted_by, '(sin coordinador)') AS coordinador,
    COUNT(*) FILTER (WHERE status = 'confirmed')   AS confirmados,
    COUNT(*) FILTER (WHERE status = 'checked_in')  AS checkeados,
    COUNT(*) FILTER (WHERE status = 'rejected')    AS rechazados,
    COUNT(*) AS total
FROM event_assignments
WHERE event_id = :'EVENT_ID'::uuid
GROUP BY admitted_by
ORDER BY total DESC;