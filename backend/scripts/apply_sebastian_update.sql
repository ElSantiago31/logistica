-- ============================================================
--  SEBASTIAN A: Crear asignaciones faltantes + UPDATE programmed_by
-- ============================================================
--  Evento: 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1 (Claro FutbolFest)
--  Total cédulas: 19 (únicas, sin duplicados)
--
--  Nota: Algunas cédulas podrían solaparse con otros coordinadores.
--  Este UPDATE sobreescribe el coordinador previo → SEBASTIAN A.
-- ============================================================

BEGIN;

-- ============================================================
--  PASO 1: Crear event_assignments faltantes
-- ============================================================
WITH cedulas_sebastian (doc) AS (
    VALUES
        ('1012427777'),('1024505006'),('80808018'),('80117415'),('1075668985'),
        ('1024568175'),('1140916089'),('52786378'),('1033794372'),('1033801477'),
        ('1029280880'),('1011086124'),('1010107477'),('1000272057'),('1033795730'),
        ('1000593625'),('1001064958'),('1024599746'),('52769557')
),
target_operators AS (
    SELECT o.id AS operator_id
    FROM operators o
    JOIN users u ON u.id = o.user_id
    WHERE u.document_number IN (SELECT doc FROM cedulas_sebastian)
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
    to2.operator_id,
    (SELECT id FROM fallback_role),
    'confirmed',
    NOW(),
    true,
    false,
    'SEBASTIAN A'
FROM target_operators to2
WHERE NOT EXISTS (
    SELECT 1 FROM event_assignments ea
    WHERE ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
      AND ea.operator_id = to2.operator_id
)
ON CONFLICT DO NOTHING;

-- ============================================================
--  PASO 2: UPDATE programmed_by = 'SEBASTIAN A'
-- ============================================================
UPDATE event_assignments ea
SET programmed_by = 'SEBASTIAN A'
FROM operators o
JOIN users u ON u.id = o.user_id
WHERE ea.operator_id = o.id
  AND ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND u.document_number IN (
        '1012427777','1024505006','80808018','80117415','1075668985',
        '1024568175','1140916089','52786378','1033794372','1033801477',
        '1029280880','1011086124','1010107477','1000272057','1033795730',
        '1000593625','1001064958','1024599746','52769557'
  );

-- ============================================================
--  VERIFICACIÓN FINAL
-- ============================================================
SELECT 'SEBASTIAN A (evento Claro)' AS metrica, COUNT(*) AS valor
FROM event_assignments
WHERE programmed_by = 'SEBASTIAN A'
  AND event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
UNION ALL
SELECT 'NICOLAS P (evento Claro)', COUNT(*)
FROM event_assignments
WHERE programmed_by = 'NICOLAS P'
  AND event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
UNION ALL
SELECT 'NAREM (evento Claro)', COUNT(*)
FROM event_assignments
WHERE programmed_by = 'NAREM'
  AND event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
UNION ALL
SELECT 'CLAUDIA B (evento Claro)', COUNT(*)
FROM event_assignments
WHERE programmed_by = 'CLAUDIA B'
  AND event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
UNION ALL
SELECT 'STEVEN O (evento Claro)', COUNT(*)
FROM event_assignments
WHERE programmed_by = 'STEVEN O'
  AND event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
UNION ALL
SELECT 'XIMENA H (evento Claro)', COUNT(*)
FROM event_assignments
WHERE programmed_by = 'XIMENA H'
  AND event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
UNION ALL
SELECT 'Total evento Claro', COUNT(*)
FROM event_assignments
WHERE event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid;

COMMIT;