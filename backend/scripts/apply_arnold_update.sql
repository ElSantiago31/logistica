-- ============================================================
--  ARNOLD R: Crear asignaciones faltantes + UPDATE programmed_by
-- ============================================================
--  Evento: 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1 (Claro FutbolFest)
--  Total cédulas: 40 (únicas, sin duplicados)
--
--  Nota: Algunas cédulas podrían solaparse con otros coordinadores.
--  Este UPDATE sobreescribe el coordinador previo → ARNOLD R.
-- ============================================================

BEGIN;

-- ============================================================
--  PASO 1: Crear event_assignments faltantes
-- ============================================================
WITH cedulas_arnold (doc) AS (
    VALUES
        ('52975382'),('1033800624'),('52463076'),('1015414478'),('1000321450'),
        ('52927052'),('1013114703'),('1000336855'),('39542297'),('1031184108'),
        ('1015414972'),('1007072243'),('1000689568'),('1010207065'),('1000457961'),
        ('1031149400'),('1010219763'),('52768450'),('1031178262'),('1013118860'),
        ('44151957'),('1023973060'),('1024566212'),('1073671971'),('1026590236'),
        ('1034277644'),('1027521493'),('1016016418'),('1019002105'),('1024557218'),
        ('79860386'),('1033791736'),('1015438214'),('1030565831'),('1105058206'),
        ('52900892'),('1032679165'),('52817009'),('1011093558'),('72238161')
),
target_operators AS (
    SELECT o.id AS operator_id
    FROM operators o
    JOIN users u ON u.id = o.user_id
    WHERE u.document_number IN (SELECT doc FROM cedulas_arnold)
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
    'ARNOLD R'
FROM target_operators to2
WHERE NOT EXISTS (
    SELECT 1 FROM event_assignments ea
    WHERE ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
      AND ea.operator_id = to2.operator_id
)
ON CONFLICT DO NOTHING;

-- ============================================================
--  PASO 2: UPDATE programmed_by = 'ARNOLD R'
-- ============================================================
UPDATE event_assignments ea
SET programmed_by = 'ARNOLD R'
FROM operators o
JOIN users u ON u.id = o.user_id
WHERE ea.operator_id = o.id
  AND ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND u.document_number IN (
        '52975382','1033800624','52463076','1015414478','1000321450',
        '52927052','1013114703','1000336855','39542297','1031184108',
        '1015414972','1007072243','1000689568','1010207065','1000457961',
        '1031149400','1010219763','52768450','1031178262','1013118860',
        '44151957','1023973060','1024566212','1073671971','1026590236',
        '1034277644','1027521493','1016016418','1019002105','1024557218',
        '79860386','1033791736','1015438214','1030565831','1105058206',
        '52900892','1032679165','52817009','1011093558','72238161'
  );

-- ============================================================
--  VERIFICACIÓN FINAL
-- ============================================================
SELECT 'ARNOLD R (evento Claro)' AS metrica, COUNT(*) AS valor
FROM event_assignments
WHERE programmed_by = 'ARNOLD R'
  AND event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
UNION ALL
SELECT 'SEBASTIAN A (evento Claro)', COUNT(*)
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