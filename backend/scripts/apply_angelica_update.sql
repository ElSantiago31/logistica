-- ============================================================
--  ANGELICA: Crear asignaciones faltantes + UPDATE programmed_by
-- ============================================================
--  Evento: 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1 (Claro FutbolFest)
--  Total cédulas: 36 (únicas tras eliminar 1 duplicado)
--
--  Duplicado eliminado: 1076716205 (aparecía 2 veces)
--
--  Nota: Algunas cédulas podrían solaparse con otros coordinadores.
--  Este UPDATE sobreescribe el coordinador previo → ANGELICA.
-- ============================================================

BEGIN;

-- ============================================================
--  PASO 1: Crear event_assignments faltantes
-- ============================================================
WITH cedulas_angelica (doc) AS (
    VALUES
        ('1120954479'),('1024580721'),('1028942524'),('1023016320'),('1032359516'),
        ('1053123293'),('1026262723'),('1026269274'),('1014667225'),('1076716205'),
        ('1106788251'),('1024510394'),('1000730887'),('1019033186'),('80141002'),
        ('1015405733'),('1019052321'),('1011087481'),('1007105313'),('1014273105'),
        ('1015402337'),('1024592431'),('1024583010'),('1030635646'),('1018505421'),
        ('1018421924'),('1031642997'),('1023030374'),('1000364848'),('79993338'),
        ('1025538252'),('1000377135'),('1024592792'),('1016714020'),('1016716305')
),
target_operators AS (
    SELECT o.id AS operator_id
    FROM operators o
    JOIN users u ON u.id = o.user_id
    WHERE u.document_number IN (SELECT doc FROM cedulas_angelica)
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
    'ANGELICA'
FROM target_operators to2
WHERE NOT EXISTS (
    SELECT 1 FROM event_assignments ea
    WHERE ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
      AND ea.operator_id = to2.operator_id
)
ON CONFLICT DO NOTHING;

-- ============================================================
--  PASO 2: UPDATE programmed_by = 'ANGELICA'
-- ============================================================
UPDATE event_assignments ea
SET programmed_by = 'ANGELICA'
FROM operators o
JOIN users u ON u.id = o.user_id
WHERE ea.operator_id = o.id
  AND ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND u.document_number IN (
        '1120954479','1024580721','1028942524','1023016320','1032359516',
        '1053123293','1026262723','1026269274','1014667225','1076716205',
        '1106788251','1024510394','1000730887','1019033186','80141002',
        '1015405733','1019052321','1011087481','1007105313','1014273105',
        '1015402337','1024592431','1024583010','1030635646','1018505421',
        '1018421924','1031642997','1023030374','1000364848','79993338',
        '1025538252','1000377135','1024592792','1016714020','1016716305'
  );

-- ============================================================
--  VERIFICACIÓN FINAL
-- ============================================================
SELECT 'ANGELICA (evento Claro)' AS metrica, COUNT(*) AS valor
FROM event_assignments
WHERE programmed_by = 'ANGELICA'
  AND event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
UNION ALL
SELECT 'ARNOLD R (evento Claro)', COUNT(*)
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