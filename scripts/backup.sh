#!/bin/bash
# ============================================================
# BACKUP AUTOMÁTICO — Logística A&C
# ============================================================
# Genera:
#   1. Dump de PostgreSQL (base de datos completa)
#   2. Tarball de los volumes de Docker (fotos, contenido, RUTs)
#
# Retención: KEEP_DAYS (por defecto 30 días)
# Uso manual:  bash scripts/backup.sh
# Uso automático: ver scripts/install_backup_cron.sh
# ============================================================
set -euo pipefail

# ---------- Configuración ----------
BACKUP_DIR="/home/server/backups/logistica"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_SUBDIR="${BACKUP_DIR}/${DATE}"

# Nombres de contenedores (coinciden con docker-compose.prod.yml)
PG_CONTAINER="logistica_postgres"

# Nombres de volumes (coinciden con docker-compose.prod.yml)
VOLUMES=(
  "logistica_photo_data"
  "logistica_content_data"
  "logistica_rut_data"
)

# Credenciales DB (se leen del entorno del contenedor)
PG_USER=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "${PG_CONTAINER}" \
  | grep '^POSTGRES_USER=' | cut -d= -f2)
PG_DB=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "${PG_CONTAINER}" \
  | grep '^POSTGRES_DB=' | cut -d= -f2)

# ---------- Helpers ----------
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# ---------- Inicio ----------
mkdir -p "${BACKUP_SUBDIR}"
log "=== Iniciando backup ${DATE} ==="
log "Destino: ${BACKUP_SUBDIR}"

# ---------- 1. PostgreSQL ----------
log ">> Dumping PostgreSQL (${PG_DB})..."
docker exec "${PG_CONTAINER}" pg_dump -U "${PG_USER}" -d "${PG_DB}" --format=plain \
  > "${BACKUP_SUBDIR}/database.sql"
log "   OK ($(du -sh "${BACKUP_SUBDIR}/database.sql" | cut -f1))"

# ---------- 2. Docker Volumes ----------
for vol in "${VOLUMES[@]}"; do
  log ">> Backup del volume: ${vol}"
  docker run --rm -v "${vol}:/data:ro" -v "${BACKUP_SUBDIR}:/backup" alpine \
    tar czf "/backup/${vol}.tar.gz" -C /data . 2>/dev/null
  log "   OK ($(du -sh "${BACKUP_SUBDIR}/${vol}.tar.gz" | cut -f1))"
done

# ---------- 3. Resumen y manifiesto ----------
{
  echo "Backup Logística A&C — ${DATE}"
  echo "Host: $(hostname)"
  echo ""
  echo "Contenidos:"
  ls -lh "${BACKUP_SUBDIR}"
  echo ""
  echo "Para restaurar ver: scripts/restore_backup.sh"
} > "${BACKUP_SUBDIR}/MANIFEST.txt"

log ">> Backup completado: ${BACKUP_SUBDIR}"

# ---------- 4. Rotación (borrar backups viejos) ----------
DELETED=$(find "${BACKUP_DIR}" -maxdepth 1 -type d -name "20*" -mtime +${KEEP_DAYS} | wc -l)
if [ "${DELETED}" -gt 0 ]; then
  log ">> Rotación: eliminando ${DELETED} backup(s) mayores a ${KEEP_DAYS} días..."
  find "${BACKUP_DIR}" -maxdepth 1 -type d -name "20*" -mtime +${KEEP_DAYS} -exec rm -rf {} +
  log "   OK"
fi

# ---------- 5. Espacio usado ----------
TOTAL=$(du -sh "${BACKUP_DIR}" | cut -f1)
log "=== Backup finalizado. Total en disco: ${TOTAL} ==="