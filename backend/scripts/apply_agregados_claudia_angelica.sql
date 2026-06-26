-- ============================================================
--  AGREGADOS: CLAUDIA B (3 cédulas) + ANGELICA (2 cédulas)
-- ============================================================
--  Evento: 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1 (Claro FutbolFest)
--  Total: 5 cédulas faltantes que no estaban en los SQLs previos
-- ============================================================

BEGIN;

-- ============================================================
--  CLAUDIA B: 3 cédulas faltantes
-- ============================================================
WITH cedulas_claudia_add (doc) AS (
    VALUES ('5044951'),('1192757762'),('1005581911')
),
target_operators_claudia AS (
    SELECT o.id AS operator_id
    FROM operators o
    JOIN users u ON u.id = o.user_id
    WHERE u.document_number IN (SELECT doc FROM cedulas_claudia_add)
      AND u.is_active = true
),
fallback_role AS (
    SELECT id FROM roles
    WHERE slug IN ('operador_logistico', 'operador_logisticos')
       OR name ILIKE '%operador logist%'
    LIMIT 1
)
INSERT INTO event_assignments (
    id, event_id, operator_id, role_id,
    status, confirmed_at, is_active, reminder_sent, programmed_by
)
SELECT
    gen_random_uuid(),
    '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid,
    toc.operator_id,
    (SELECT id FROM fallback_role),
    'confirmed',
    NOW(),
    true,
    false,
    'CLAUDIA B'
FROM target_operators_claudia toc
WHERE NOT EXISTS (
    SELECT 1 FROM event_assignments ea
    WHERE ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
      AND ea.operator_id = toc.operator_id
)
ON CONFLICT DO NOTHING;

UPDATE event_assignments ea
SET programmed_by = 'CLAUDIA B'
FROM operators o
JOIN users u ON u.id = o.user_id
WHERE ea.operator_id = o.id
  AND ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND u.document_number IN ('5044951','1192757762','1005581911');

-- ============================================================
--  ANGELICA: 2 cédulas faltantes
-- ============================================================
WITH cedulas_angelica_add (doc) AS (
    VALUES ('1000617894'),('1233902135')
),
target_operators_angelica AS (
    SELECT o.id AS operator_id
    FROM operators o
    JOIN users u ON u.id = o.user_id
    WHERE u.document_number IN (SELECT doc FROM cedulas_angelica_add)
      AND u.is_active = true
),
fallback_role2 AS (
    SELECT id FROM roles
    WHERE slug IN ('operador_logistico', 'operador_logisticos')
       OR name ILIKE '%operador logist%'
    LIMIT 1
)
INSERT INTO event_assignments (
    id, event_id, operator_id, role_id,
    status, confirmed_at, is_active, reminder_sent, programmed_by
)
SELECT
    gen_random_uuid(),
    '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid,
    toa.operator_id,
    (SELECT id FROM fallback_role2),
    'confirmed',
    NOW(),
    true,
    false,
    'ANGELICA'
FROM target_operators_angelica toa
WHERE NOT EXISTS (
    SELECT 1 FROM event_assignments ea
    WHERE ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
      AND ea.operator_id = toa.operator_id
)
ON CONFLICT DO NOTHING;

UPDATE event_assignments ea
SET programmed_by = 'ANGELICA'
FROM operators o
JOIN users u ON u.id = o.user_id
WHERE ea.operator_id = o.id
  AND ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND u.document_number IN ('1000617894','1233902135');

COMMIT;