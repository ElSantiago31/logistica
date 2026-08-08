#!/bin/bash
# ============================================================
# INSTALADOR DE BACKUP AUTOMÁTICO (CRON) — Logística A&C
# ============================================================
# Configura cron para ejecutar backups automáticos:
#   - Diario a las 03:00 AM (backup completo)
#
# Retención por defecto: 30 días (configurable en el script backup.sh)
#
# Uso (en la VPS, como root):
#   sudo bash scripts/install_backup_cron.sh
# ============================================================
set -euo pipefail

REPO_DIR="/opt/logistica"
BACKUP_SCRIPT="${REPO_DIR}/scripts/backup.sh"
LOG_FILE="/var/log/logistica-backup.log"
CRON_SCHEDULE="0 3 * * *"   # Diario a las 3:00 AM
CRON_MARKER="# logistica-auto-backup"

echo "=== Instalador de backup automático ==="

# ---------- 1. Validar que el script exista ----------
if [ ! -f "${BACKUP_SCRIPT}" ]; then
  echo "ERROR: No se encuentra ${BACKUP_SCRIPT}"
  echo "¿Estás en /opt/logistica? ¿Hiciste git pull?"
  exit 1
fi

chmod +x "${BACKUP_SCRIPT}"
echo "OK: Script encontrado en ${BACKUP_SCRIPT}"

# ---------- 2. Crear directorio de backups ----------
mkdir -p /opt/backups/logistica
echo "OK: Directorio de backups: /opt/backups/logistica"

# ---------- 3. Instalar cron ----------
# Eliminar entrada previa (si existe) para no duplicar
crontab -l 2>/dev/null | grep -v "${CRON_MARKER}" > /tmp/crontab_new || true

# Agregar la nueva entrada
echo "${CRON_SCHEDULE} cd ${REPO_DIR} && bash ${BACKUP_SCRIPT} >> ${LOG_FILE} 2>&1 ${CRON_MARKER}" >> /tmp/crontab_new

crontab /tmp/crontab_new
rm -f /tmp/crontab_new

echo "OK: Cron instalado (diario a las 03:00 AM)"

# ---------- 4. Confirmación ----------
echo ""
echo "=== Instalación completada ==="
echo "  Script:     ${BACKUP_SCRIPT}"
echo "  Destino:    /opt/backups/logistica/"
echo "  Log:        ${LOG_FILE}"
echo "  Cron:       ${CRON_SCHEDULE} (diario)"
echo "  Retención:  30 días"
echo ""
echo "Para ver los cron jobs instalados:"
echo "  crontab -l"
echo ""
echo "Para ejecutar un backup AHORA (prueba manual):"
echo "  bash ${BACKUP_SCRIPT}"
echo ""
echo "Para DESINSTALAR el cron:"
echo "  crontab -l | grep -v '${CRON_MARKER}' | crontab -"