-- ============================================================
--  STEVEN O: Crear asignaciones faltantes + UPDATE programmed_by
-- ============================================================
--  Evento: 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1 (Claro FutbolFest)
--  Total cédulas: 75 (sin duplicados)
--
--  Nota: 4 cédulas se solapan con XIMENA H (1045716230, 1005829350,
--  1233694394, 5715207). Este UPDATE sobreescribe XIMENA H → STEVEN O
--  porque STEVEN es el coordinador que los programó.
-- ============================================================

BEGIN;

-- ============================================================
--  PASO 1: Crear event_assignments faltantes
-- ============================================================
WITH cedulas_steven (doc) AS (
    VALUES
        ('10124513701'),('1023947731'),('1025320332'),('8405356'),('1018411733'),
        ('52763208'),('1006407457'),('1014191982'),('1120369210'),('1021670928'),
        ('1007172880'),('1045742955'),('1031179849'),('1028862681'),('1030538002'),
        ('1193140489'),('1014260906'),('1007157616'),('52747242'),('1034278837'),
        ('1000777747'),('1011323762'),('52239142'),('1030706267'),('1010226748'),
        ('1022960935'),('1045716230'),('3117679334'),('1000062104'),('1023968139'),
        ('1016045874'),('1033817606'),('1105789139'),('1001059450'),('1143147718'),
        ('80178401'),('5715207'),('1000726164'),('1002580753'),('1055750608'),
        ('1005829350'),('1001873620'),('1001053566'),('1025524261'),('1014253373'),
        ('1018506350'),('1018491782'),('1033789805'),('79859338'),('1003879631'),
        ('1022969899'),('51857041'),('53094514'),('1022969900'),('1030535967'),
        ('1000352497'),('51839593'),('1043146922'),('1016948719'),('52726708'),
        ('1021664710'),('5489854'),('79900522'),('80024779'),('1007675497'),
        ('52737768'),('1233694394'),('1002979610'),('1021668722'),('1026561059'),
        ('6523788'),('53135634'),('1073704823'),('1033785119')
),
target_operators AS (
    SELECT o.id AS operator_id
    FROM operators o
    JOIN users u ON u.id = o.user_id
    WHERE u.document_number IN (SELECT doc FROM cedulas_steven)
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
    'STEVEN O'
FROM target_operators to2
WHERE NOT EXISTS (
    SELECT 1 FROM event_assignments ea
    WHERE ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
      AND ea.operator_id = to2.operator_id
)
ON CONFLICT DO NOTHING;

-- ============================================================
--  PASO 2: UPDATE programmed_by = 'STEVEN O'
--  (incluye los 4 que estaban como XIMENA H)
-- ============================================================
UPDATE event_assignments ea
SET programmed_by = 'STEVEN O'
FROM operators o
JOIN users u ON u.id = o.user_id
WHERE ea.operator_id = o.id
  AND ea.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND u.document_number IN (
        '10124513701','1023947731','1025320332','8405356','1018411733',
        '52763208','1006407457','1014191982','1120369210','1021670928',
        '1007172880','1045742955','1031179849','1028862681','1030538002',
        '1193140489','1014260906','1007157616','52747242','1034278837',
        '1000777747','1011323762','52239142','1030706267','1010226748',
        '1022960935','1045716230','3117679334','1000062104','1023968139',
        '1016045874','1033817606','1105789139','1001059450','1143147718',
        '80178401','5715207','1000726164','1002580753','1055750608',
        '1005829350','1001873620','1001053566','1025524261','1014253373',
        '1018506350','1018491782','1033789805','79859338','1003879631',
        '1022969899','51857041','53094514','1022969900','1030535967',
        '1000352497','51839593','1043146922','1016948719','52726708',
        '1021664710','5489854','79900522','80024779','1007675497',
        '52737768','1233694394','1002979610','1021668722','1026561059',
        '6523788','53135634','1073704823','1033785119'
  );

-- ============================================================
--  VERIFICACIÓN FINAL
-- ============================================================
SELECT 'STEVEN O (evento Claro)' AS metrica, COUNT(*) AS valor
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