-- ============================================================
--  AGREGAR OPERADOR al evento 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1
-- ============================================================
--  Cédula operador : 1013642667
--  Evento          : 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1 (Claro FutbolFest)
--  Coordinador     : CLAUDIA B  (programmed_by / admitted_by)
--  Status          : confirmed
-- ============================================================
--  USO (en la VPS de producción):
--    docker exec -i logistica_postgres psql -U logistica -d logistica \
--      < backend/scripts/add_operator_to_event.sql
-- ============================================================

\set EVENT_ID '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'
\set CEDULA   '1013642667'
\set COORD    'CLAUDIA B'

BEGIN;

-- ------------------------------------------------------------
--  0) Mostrar a quién vamos a agregar (para el log)
-- ------------------------------------------------------------
SELECT
    u.document_number AS cedula,
    u.first_name || ' ' || u.last_name AS nombre,
    u.phone,
    o.id AS operator_id
FROM users u
JOIN operators o ON o.user_id = u.id
WHERE u.document_number = :'CEDULA';

-- ------------------------------------------------------------
--  1) VALIDACIONES previas (abortan si algo falla)
-- ------------------------------------------------------------
DO $$
DECLARE
    v_operator_id uuid;
    v_event_exists boolean;
    v_already_assigned boolean;
BEGIN
    -- (a) ¿Existe el operador con esa cédula?
    SELECT o.id INTO v_operator_id
    FROM users u
    JOIN operators o ON o.user_id = u.id
    WHERE u.document_number = :'CEDULA';

    IF v_operator_id IS NULL THEN
        RAISE EXCEPTION 'OPERADOR NO ENCONTRADO: no existe usuario/operador con cédula %', :'CEDULA';
    END IF;

    -- (b) ¿Existe el evento?
    SELECT EXISTS(
        SELECT 1 FROM events WHERE id = :'EVENT_ID'::uuid
    ) INTO v_event_exists;

    IF NOT v_event_exists THEN
        RAISE EXCEPTION 'EVENTO NO ENCONTRADO: no existe el evento %', :'EVENT_ID';
    END IF;

    -- (c) ¿Ya está asignado a este evento? (anti-duplicados)
    SELECT EXISTS(
        SELECT 1 FROM event_assignments
        WHERE event_id = :'EVENT_ID'::uuid
          AND operator_id = v_operator_id
    ) INTO v_already_assigned;

    IF v_already_assigned THEN
        RAISE EXCEPTION 'YA ASIGNADO: el operador con cédula % ya está en el evento %', :'CEDULA', :'EVENT_ID';
    END IF;

    RAISE NOTICE 'Validaciones OK. operator_id=%', v_operator_id;
END $$;

-- ------------------------------------------------------------
--  2) INSERTAR la asignación
-- ------------------------------------------------------------
INSERT INTO event_assignments (
    id, event_id, operator_id, role_id, status,
    programmed_by, admitted_by,
    reminder_sent, invited_at, confirmed_at,
    created_at, updated_at, is_active
)
SELECT
    gen_random_uuid(),
    :'EVENT_ID'::uuid,
    o.id,
    NULL,                       -- role_id (sin rol específico)
    'confirmed',                -- status
    :'COORD',                   -- programmed_by
    :'COORD',                   -- admitted_by  (cupo descuenta de acá)
    false,                      -- reminder_sent (NOT NULL)
    NOW(),                      -- invited_at
    NOW(),                      -- confirmed_at
    NOW(),                      -- created_at
    NOW(),                      -- updated_at
    true                        -- is_active
FROM users u
JOIN operators o ON o.user_id = u.id
WHERE u.document_number = :'CEDULA';

COMMIT;

-- ============================================================
--  3) VERIFICACIÓN FINAL
-- ============================================================
\echo ''
\echo '========== VERIFICACIÓN =========='

SELECT
    u.document_number AS cedula,
    u.first_name || ' ' || u.last_name AS nombre,
    ea.status,
    ea.programmed_by,
    ea.admitted_by,
    ea.confirmed_at
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
    COUNT(*) AS total
FROM event_assignments
WHERE event_id = :'EVENT_ID'::uuid
GROUP BY admitted_by
ORDER BY total DESC;