-- ============================================================
--  SEED: Cupos por coordinador — Claro FutbolFest
-- ============================================================
--  Evento: 13e549bf-fe1b-4bb3-9887-5c48bf0a25c1
--  Tabla:  event_coordinator_quotas
-- ============================================================
--  Cupos máximos (nombres corregidos según producción):
--    CLAUDIA B:    100   (191 operadores asignados)
--    NICOLAS P:     80   (163 operadores asignados)
--    XIMENA H:     100   (160 operadores asignados)
--    STEVEN O:      15   ( 70 operadores asignados)
--    ANGELICA:      24   ( 35 operadores asignados)
--    NAREM:         20   ( 30 operadores asignados)
--    SEBASTIAN A:   15   ( 19 operadores asignados)
--    ARNOLD R:      21   ( 12 operadores asignados)
--    ALEJANDRO:     25   (  1 operador  asignado)
--    SANDRA:        85   (  0 operadores, pendiente de cargar)
-- ============================================================
--  NOTA: Esta tabla guarda el cupo MAXIMO permitido por coordinador.
--  El conteo en vivo se hace desde la API contando event_assignments
--  WHERE status = 'checked_in' AND admitted_by = '<COORDINADOR>'.
-- ============================================================

BEGIN;

INSERT INTO event_coordinator_quotas (id, event_id, coordinator, quota, is_active, created_at, updated_at)
SELECT
    gen_random_uuid(),
    '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid,
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
    WHERE ecq.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
      AND ecq.coordinator = coord.coord_name
)
ON CONFLICT DO NOTHING;

COMMIT;

-- ============================================================
--  ACTUALIZAR cupos si ya existen (por si hubo cambios)
-- ============================================================
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
WHERE event_coordinator_quotas.event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid
  AND event_coordinator_quotas.coordinator = vals.coord_name;

-- ============================================================
--  VERIFICACIÓN (ejecutar manualmente después del seed)
-- ============================================================
-- SELECT coordinator, quota, is_active FROM event_coordinator_quotas
-- WHERE event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'
-- ORDER BY quota DESC, coordinator;
-- ============================================================

-- ============================================================
--  BACKFILL admitted_by = programmed_by (si no se ejecutó en la migración)
-- ============================================================
UPDATE event_assignments
SET admitted_by = programmed_by
WHERE admitted_by IS NULL
  AND programmed_by IS NOT NULL
  AND event_id = '13e549bf-fe1b-4bb3-9887-5c48bf0a25c1'::uuid;