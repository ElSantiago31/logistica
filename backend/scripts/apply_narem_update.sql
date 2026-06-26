-- ============================================================
--  NAREM: Crear asignaciones faltantes + UPDATE programmed_by
-- ============================================================
--  Evento: 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1 (Claro FutbolFest)
--  Total cédulas: 30 (únicas)
--
--  Nota: 2 cédulas se solapan con XIMENA H y STEVEN O:
--  1045716230 y 1005829350. Este UPDATE sobreescribe → NAREM.
-- ============================================================

BEGIN;

-- ============================================================
--  PASO 1: Crear event_assignments faltantes
-- ============================================================
WITH cedulas_narem (doc) AS (
    VALUES
        ('1012317131'),('1023949699'),('1000777320'),('80235269'),('1023932709'),
        ('1000134599'),('1044214063'),('1046812286'),('1028840556'),('52875619'),
        ('52833807'),('1047233698'),('1033780698'),('1013120805'),('1000223295'),
        ('1031131326'),('1053329672'),('1045716230'),('1015469688'),('1233695712'),
        ('1028885250'),('1013602637'),('1102798216'),('1005829350'),('1021669927'),
        ('1033693544'),('52774030'),('1015455222'),('1001948129'),('12021676')
),
target_operators AS (
    SELECT o.id AS operator_id
    FROM operators o
    JOIN users u ON u.id = o.user_id
    WHERE u.document_number IN (SELECT doc FROM cedulas_narem)
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
    'NAREM'
FROM target_operators to2
WHERE NOT EXISTS (
    SELECT 1 FROM event_assignments ea
    WHERE ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
      AND ea.operator_id = to2.operator_id
)
ON CONFLICT DO NOTHING;

-- ============================================================
--  PASO 2: UPDATE programmed_by = 'NAREM'
-- ============================================================
UPDATE event_assignments ea
SET programmed_by = 'NAREM'
FROM operators o
JOIN users u ON u.id = o.user_id
WHERE ea.operator_id = o.id
  AND ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND u.document_number IN (
        '1012317131','1023949699','1000777320','80235269','1023932709',
        '1000134599','1044214063','1046812286','1028840556','52875619',
        '52833807','1047233698','1033780698','1013120805','1000223295',
        '1031131326','1053329672','1045716230','1015469688','1233695712',
        '1028885250','1013602637','1102798216','1005829350','1021669927',
        '1033693544','52774030','1015455222','1001948129','12021676'
  );

-- ============================================================
--  VERIFICACIÓN FINAL
-- ============================================================
SELECT 'NAREM (evento Claro)' AS metrica, COUNT(*) AS valor
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