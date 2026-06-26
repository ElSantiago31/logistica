-- ============================================================
--  SEED: Cupos por coordinador — Evento de PRUEBA en producción
-- ============================================================
--  Evento: 49325566-b746-4ce1-9783-3b4fee0536b6
--  Tabla:  event_coordinator_quotas
-- ============================================================
--  Cupos máximos (mismos nombres de producción):
--    CLAUDIA B:    100
--    NICOLAS P:     80
--    XIMENA H:     100
--    STEVEN O:      15
--    ANGELICA:      24
--    NAREM:         20
--    SEBASTIAN A:   15
--    ARNOLD R:      21
--    ALEJANDRO:     25
--    SANDRA:        85
-- ============================================================
--  NOTA: Este evento es de PRUEBA. Eliminar al final junto con
--  sus cupos (DELETE FROM event_coordinator_quotas WHERE event_id = ...).
-- ============================================================

BEGIN;

INSERT INTO event_coordinator_quotas (id, event_id, coordinator, quota, is_active, created_at, updated_at)
SELECT
    gen_random_uuid(),
    '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid,
    coord.coord_name,
    coord.quota_val,
    true,
    NOW(),
    NOW()
FROM (VALUES
    ('CLAUDIA B',    100),
    ('NICOLAS P',     80),
    ('XIMENA H',    100),
    ('STEVEN O',      15),
    ('ANGELICA',      24),
    ('NAREM',         20),
    ('SEBASTIAN A',   15),
    ('ARNOLD R',      21),
    ('ALEJANDRO',     25),
    ('SANDRA',        85)
) AS coord(coord_name, quota_val)
WHERE NOT EXISTS (
    SELECT 1 FROM event_coordinator_quotas ecq
    WHERE ecq.event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid
      AND ecq.coordinator = coord.coord_name
)
ON CONFLICT DO NOTHING;

UPDATE event_coordinator_quotas
SET quota = vals.quota_val, is_active = true, updated_at = NOW()
FROM (VALUES
    ('CLAUDIA B',    100),
    ('NICOLAS P',     80),
    ('XIMENA H',    100),
    ('STEVEN O',      15),
    ('ANGELICA',      24),
    ('NAREM',         20),
    ('SEBASTIAN A',   15),
    ('ARNOLD R',      21),
    ('ALEJANDRO',     25),
    ('SANDRA',        85)
) AS vals(coord_name, quota_val)
WHERE event_coordinator_quotas.event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid
  AND event_coordinator_quotas.coordinator = vals.coord_name;

COMMIT;

-- ============================================================
--  VERIFICACIÓN
-- ============================================================
-- SELECT coordinator, quota, is_active FROM event_coordinator_quotas
-- WHERE event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'
-- ORDER BY quota DESC, coordinator;
-- ============================================================

-- ============================================================
--  BACKFILL admitted_by = programmed_by
-- ============================================================
UPDATE event_assignments
SET admitted_by = programmed_by
WHERE admitted_by IS NULL
  AND programmed_by IS NOT NULL
  AND event_id = '49325566-b746-4ce1-9783-3b4fee0536b6'::uuid;