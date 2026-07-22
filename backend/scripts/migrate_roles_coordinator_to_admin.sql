-- ============================================================
-- MIGRACIÓN: user_type 'coordinator' -> 'admin'
-- ============================================================
-- Propósito:
--   El rol de usuario (tabla `users.user_type`) 'coordinator' otorgaba
--   acceso al panel administrativo (/admin). Tras el refactor de
--   permisos (Fase 3), ese acceso ahora corresponde al rol 'admin'.
--
--   NOTA IMPORTANTE:
--   Este 'coordinator' (user_type) es DISTINTO del coordinador de
--   evento (Role con hierarchy_level=2 en la tabla `roles`). Los
--   roles operativos de evento NO se tocan en esta migración.
--
-- Acción:
--   UPDATE users SET user_type='admin' WHERE user_type='coordinator';
--   UPDATE users SET user_type='checkin' WHERE user_type='intendencia';
--
-- Uso (producción):
--   docker exec -i logistica-db psql -U <user> -d <db> < scripts/migrate_roles_coordinator_to_admin.sql
--
-- Uso (local con Docker):
--   docker compose exec -T db psql -U postgres -d logistica < backend/scripts/migrate_roles_coordinator_to_admin.sql
--
-- Es SEGURO ejecutarlo múltiples veces (idempotente).
-- ============================================================

BEGIN;

-- 1) Reporte PRE-migración (para auditoría)
\echo '=== ANTES de la migración ==='
SELECT user_type, COUNT(*) AS total
FROM users
GROUP BY user_type
ORDER BY user_type;

-- 2) Migrar coordinadores (con acceso a /admin) -> admin
UPDATE users
SET user_type = 'admin',
    updated_at = NOW()
WHERE user_type = 'coordinator';

-- 3) Migrar intendencia -> checkin (rol unificado)
--    (intendencia fue removido; sus funciones las asume checkin)
UPDATE users
SET user_type = 'checkin',
    updated_at = NOW()
WHERE user_type = 'intendencia';

-- 4) Reporte POST-migración
\echo '=== DESPUÉS de la migración ==='
SELECT user_type, COUNT(*) AS total
FROM users
GROUP BY user_type
ORDER BY user_type;

COMMIT;

-- ============================================================
-- ROLLBACK (en caso de necesitar revertir):
--
-- BEGIN;
-- UPDATE users SET user_type='coordinator' WHERE user_type='admin';
-- COMMIT;
--
-- ADVERTENCIA: El rollback es destructivo si se crearon usuarios
-- 'admin' NUEVOS después de la migración (se convertirían en
-- 'coordinator'). Revisar manualmente antes de revertir.
-- ============================================================