-- ============================================================
--  SEED: Cupos por coordinador — Claro FutbolFest
-- ============================================================
--  Evento: 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1
--  Tabla:  event_coordinator_quotas
-- ============================================================
--  Cupos máximos:
--    ALEJANDRO:  25
--    ANGELICA:   24
--    ARNOLD:     21
--    CLAUDIA:   100
--    NAREM:      20
--    PACHECO:    80
--    SEBASTIAN:  15
--    XIMENA:    100
--    SANDRA:     85
-- ============================================================
--  NOTA: Esta tabla guarda el cupo MAXIMO permitido por coordinador.
--  El conteo en vivo se hace desde la API contando event_assignments
--  WHERE status = 'checked_in' AND admitted_by = '<COORDINADOR>'.
-- ============================================================

BEGIN;

INSERT INTO event_coordinator_quotas (id, event_id, coordinator, quota, created_at, updated_at)
SELECT
    gen_random_uuid(),
    '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid,
    coord.coord_name,
    coord.quota_val,
    NOW(),
    NOW()
FROM (VALUES
    ('ALEJANDRO', 25),
    ('ANGELICA',  24),
    ('ARNOLD',    21),
    ('CLAUDIA',  100),
    ('NAREM',     20),
    ('PACHECO',   80),
    ('SEBASTIAN', 15),
    ('XIMENA',   100),
    ('SANDRA',    85)
) AS coord(coord_name, quota_val)
WHERE NOT EXISTS (
    SELECT 1 FROM event_coordinator_quotas ecq
    WHERE ecq.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
      AND ecq.coordinator = coord.coord_name
)
ON CONFLICT DO NOTHING;

COMMIT;

-- ============================================================
--  VERIFICACIÓN (ejecutar manualmente después del seed)
-- ============================================================
-- SELECT coordinator, quota FROM event_coordinator_quotas
-- WHERE event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'
-- ORDER BY coordinator;
-- ============================================================

-- ============================================================
--  BACKFILL admitted_by = programmed_by (si no se ejecutó en la migración)
-- ============================================================
UPDATE event_assignments
SET admitted_by = programmed_by
WHERE admitted_by IS NULL
  AND programmed_by IS NOT NULL
  AND event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid;