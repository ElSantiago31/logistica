#!/bin/bash
# ============================================================
# RESTAURACIÓN DE BACKUP — Logística A&C
# ============================================================
# Restaura un backup generado por scripts/backup.sh
#
# Uso:
#   bash scripts/restore_backup.sh <fecha_backup>
#   bash scripts/restore_backup.sh 20260808_160200
#
# ADVERTENCIA: Sobrescribe la BD y los archivos actuales.
#              Haz un backup del estado actual ANTES de restaurar.
# ============================================================
set -euo pipefail

# ---------- Validaciones ----------
if [ "$#" -ne 1 ]; then
  echo "Uso: bash scripts/restore_backup.sh <fecha_backup>"
  echo "Ejemplo: bash scripts/restore_backup.sh 20260808_160200"
  echo ""
  echo "Backups disponibles:"
  ls -1 /home/server/backups/logistica/ 2>/dev/null | grep -E '^[0-9]{8}_[0-9]{6}$' || echo "  (ninguno)"
  exit 1
fi

BACKUP_DIR="/home/server/backups/logistica"
DATE="$1"
BACKUP_PATH="${BACKUP_DIR}/${DATE}"

if [ ! -d "${BACKUP_PATH}" ]; then
  echo "ERROR: No existe el backup '${BACKUP_PATH}'"
  echo "Backups disponibles:"
  ls -1 "${BACKUP_DIR}" 2>/dev/null | grep -E '^[0-9]{8}_[0-9]{6}$' || echo "  (ninguno)"
  exit 1
fi

PG_CONTAINER="logistica_postgres"
PG_USER=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "${PG_CONTAINER}" \
  | grep '^POSTGRES_USER=' | cut -d= -f2)
PG_DB=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "${PG_CONTAINER}" \
  | grep '^POSTGRES_DB=' | cut -d= -f2)

echo "============================================================"
echo "  RESTAURACIÓN DE BACKUP"
echo "============================================================"
echo "  Backup:   ${BACKUP_PATH}"
echo "  BD:       ${PG_DB}"
echo "  Contenido:"
ls -lh "${BACKUP_PATH}"
echo "============================================================"
echo ""
echo "⚠️  Esto SOBRESCRIBIRÁ los datos actuales."
read -p "¿Continuar? (escribe SI): " confirm
if [ "${confirm}" != "SI" ]; then
  echo "Restauración cancelada."
  exit 0
fi

# ---------- 1. PostgreSQL ----------
if [ -f "${BACKUP_PATH}/database.sql" ]; then
  echo ">> Restaurando PostgreSQL..."
  cat "${BACKUP_PATH}/database.sql" | docker exec -i "${PG_CONTAINER}" \
    psql -U "${PG_USER}" -d "${PG_DB}" 2>&1 | grep -v '^$' || true
  echo "   OK"
else
  echo ">> [SKIP] No hay database.sql en este backup"
fi

# ---------- 2. Docker Volumes ----------
for vol_tarball in "${BACKUP_PATH}"/logistica_*.tar.gz; do
  [ -f "$vol_tarball" ] || continue
  vol_name=$(basename "$vol_tarball" .tar.gz)
  echo ">> Restaurando volume: ${vol_name}"
  docker run --rm \
    -v "${vol_name}:/data" \
    -v "${BACKUP_PATH}:/backup:ro" \
    alpine sh -c "rm -rf /data/* /data/.* 2>/dev/null; tar xzf /backup/${vol_name}.tar.gz -C /data"
  echo "   OK"
done

echo ""
echo "============================================================"
echo "  RESTAURACIÓN COMPLETADA"
echo "============================================================"
echo "  Reinicia el backend para que relea los datos:"
echo "    docker restart logistica_backend"
echo "============================================================"