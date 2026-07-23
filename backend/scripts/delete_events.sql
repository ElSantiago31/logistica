-- ============================================================
-- ELIMINACION DE EVENTOS EN PRODUCCION
-- Eventos objetivo:
--   03b72292-46d1-49a9-b985-5bb62626006c
--   49325566-b746-4ce1-9783-3b4fee0536b6
--   32df43d8-4f26-4a1a-8309-437dd209c813
--
-- Uso (dentro de la VPS, en /opt/logistica):
--   docker exec -i logistica_postgres sh -c \
--     'psql -U "$POSTGRES_USER" "$POSTGRES_DB"' < backend/scripts/delete_events.sql
--
-- Nota: usamos sh -c dentro del contenedor para que expanda automáticamente
-- $POSTGRES_USER y $POSTGRES_DB (definidos en el .env del docker-compose).
-- No hardcodear nombres: el RUNBOOK usaba "logistica_user" que no existe.
--
-- Tablas afectadas por CASCADE (se borran automaticamente):
--   - event_staff_needs
--   - event_audit_logs
--   - event_assignments
--   - event_staff_assignments
--   - event_coordinator_quotas
--   - operator_incidents
--   - evaluations
--   - payroll_records
--   - sync_queue
--
-- Tabla con SET NULL (NO se borra, solo se desenlaza):
--   - whatsapp_messages.event_id -> NULL
--
-- IMPORTANTE: Correr primero un backup (ver RUNBOOK_VPS.md).
-- ============================================================

\set TARGET_IDS '''03b72292-46d1-49a9-b985-5bb62626006c'',
                  ''49325566-b746-4ce1-9783-3b4fee0536b6'',
                  ''32df43d8-4f26-4a1a-8309-437dd209c813'''

\echo '============================================================'
\echo 'PREVIEW - Filas que SE ELIMINARAN (por CASCADE):'
\echo '============================================================'

SELECT 'event_assignments'        AS tabla, count(*) AS filas FROM event_assignments        WHERE event_id IN (:TARGET_IDS)
UNION ALL SELECT 'event_staff_needs',         count(*) FROM event_staff_needs         WHERE event_id IN (:TARGET_IDS)
UNION ALL SELECT 'event_audit_logs',          count(*) FROM event_audit_logs          WHERE event_id IN (:TARGET_IDS)
UNION ALL SELECT 'event_staff_assignments',   count(*) FROM event_staff_assignments   WHERE event_id IN (:TARGET_IDS)
UNION ALL SELECT 'event_coordinator_quotas',  count(*) FROM event_coordinator_quotas  WHERE event_id IN (:TARGET_IDS)
UNION ALL SELECT 'operator_incidents',        count(*) FROM operator_incidents        WHERE event_id IN (:TARGET_IDS)
UNION ALL SELECT 'evaluations',               count(*) FROM evaluations               WHERE event_id IN (:TARGET_IDS)
UNION ALL SELECT 'payroll_records',           count(*) FROM payroll_records           WHERE event_id IN (:TARGET_IDS)
UNION ALL SELECT 'sync_queue',                count(*) FROM sync_queue                WHERE event_id IN (:TARGET_IDS);

\echo ''
\echo 'Eventos a borrar:'
SELECT id, name, status, start_date
FROM events
WHERE id IN (:TARGET_IDS);

\echo ''
\echo '============================================================'
\echo 'ATENCION: Revisa el conteo arriba. Si es correcto, ejecuta'
\echo 'el DELETE a continuacion (esta dentro de una transaccion).'
\echo '============================================================'
\echo ''

BEGIN;

-- El DELETE propaga por ON DELETE CASCADE a todas las tablas hijas.
DELETE FROM events
WHERE id IN (
    '03b72292-46d1-49a9-b985-5bb62626006c',
    '49325566-b746-4ce1-9783-3b4fee0536b6',
    '32df43d8-4f26-4a1a-8309-437dd209c813'
);

\echo 'Eventos eliminados. Ejecuta COMMIT para confirmar o ROLLBACK para cancelar.'
-- COMMIT se ejecuta manualmente para dar una ultima oportunidad de verificar:
--   psql ya hara COMMIT al final del script, pero si prefieres pausa,
--   comenta la linea COMMIT y ejecuta el script, luego revisa y haz COMMIT a mano.

COMMIT;

\echo ''
\echo '============================================================'
\echo 'VERIFICACION POST-DELETE:'
\echo '============================================================'

SELECT id, name FROM events WHERE id IN (:TARGET_IDS);
\echo '(Si la consulta de arriba esta vacia, los eventos fueron eliminados.)'