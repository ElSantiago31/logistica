# 📖 Runbook VPS — Guía de Operaciones

> Comandos para gestionar el servidor de producción (`ayceventos.com.co`).
> Todos los comandos se ejecutan por **SSH en la VPS**, dentro de `/home/server/Logistica`.

---

## 🔄 REINICIAR SERVICIOS (sin perder datos)

### Reiniciar solo el backend (lo más común)
```bash
docker restart logistica_backend
```
**Cuándo usarlo:**
- El backend no responde o está lento
- Después de cambiar variables de entorno en `.env`
- Para limpiar conexiones de DB acumuladas

### Reiniciar solo nginx
```bash
docker restart logistica_nginx
```
**Cuándo usarlo:**
- La web no carga pero el backend sí responde
- Después de cambiar `nginx/nginx.conf`
- Error 502 Bad Gateway

### Reiniciar TODO el stack
```bash
docker compose -f docker-compose.prod.yml restart
```
**Cuándo usarlo:**
- El VPS está muy lento y necesitas reiniciar todo
- Problemas generales de conectividad
- Después de reiniciar el VPS físico (`reboot`)

---

## 🚀 ACTUALIZAR EL SISTEMA (deploy de cambios nuevos)

### Cambios de código (sin migraciones nuevas)
```bash
cd /home/server/Logistica
git pull origin master
docker compose -f docker-compose.prod.yml up -d --build
```

### Cambios con migraciones nuevas
```bash
cd /home/server/Logistica
git pull origin master
docker compose -f docker-compose.prod.yml up -d --build
# Las migraciones se ejecutan automáticamente al arrancar el backend
```

**Duración:** 3-5 minutos de downtime. Avisar a los usuarios.

---

## 🩺 DIAGNÓSTICO (cuando algo falla)

### Ver estado de todos los servicios
```bash
docker compose -f docker-compose.prod.yml ps
```
Todos deben decir `Up`. El backend debe decir `(healthy)`.

### Ver logs de un servicio
```bash
# Backend (errores de código, migraciones, API)
docker logs logistica_backend --tail 50

# Nginx (errores de SSL, proxy, 502)
docker logs logistica_nginx --tail 50

# PostgreSQL (errores de DB)
docker logs logistica_postgres --tail 50
```

### Ver logs en tiempo real
```bash
docker logs -f logistica_backend
```
Presionar `Ctrl+C` para salir.

---

## 💾 BACKUP AUTOMÁTICO

El sistema genera backups **diarios automáticos** (3:00 AM) con retención de 30 días.
Cada backup incluye: **BD completa (PostgreSQL) + fotos + imágenes de contenido + PDFs de RUT**.

### 🚀 Instalación inicial (una sola vez, en la VPS)

Después de hacer `git pull`, ejecutar:
```bash
cd /home/server/Logistica
sudo bash scripts/install_backup_cron.sh
```

Esto configura el cron job diario. **Verificar que quedó instalado:**
```bash
crontab -l | grep logistica
# Debe mostrar: 0 3 * * * cd /home/server/Logistica && bash scripts/backup.sh ...
```

### 📋 Backup manual (antes de cambios importantes)

```bash
cd /home/server/Logistica
bash scripts/backup.sh
```

### 🔙 Restaurar un backup

```bash
cd /home/server/Logistica

# Ver backups disponibles
ls /home/server/backups/logistica/

# Restaurar uno específico
bash scripts/restore_backup.sh 20260808_030000

# Reiniciar backend para que relea los datos
docker restart logistica_backend
```

### 📊 Monitorear los backups

```bash
# Ver los backups generados
ls -lh /home/server/backups/logistica/

# Ver el log de backups
tail -50 /var/log/logistica-backup.log

# Ver tamaño total de los backups
du -sh /home/server/backups/logistica/
```

### ⚙️ Configuración

| Parámetro | Valor por defecto | dónde cambiar |
|-----------|-------------------|---------------|
| Frecuencia | Diario 3:00 AM | `scripts/install_backup_cron.sh` |
| Retención | 30 días | `scripts/backup.sh` (`KEEP_DAYS`) |
| Destino | `/home/server/backups/logistica/` | `scripts/backup.sh` (`BACKUP_DIR`) |

### 🛑 Desinstalar el cron (si necesario)

```bash
crontab -l | grep -v 'logistica-auto-backup' | crontab -
```

---

## 📁 PERSISTENCIA DE ARCHIVOS (Volumes)

El sistema guarda archivos subidos por usuarios en 3 Docker volumes persistentes.
**Sin estos volumes, cada deploy pierde los archivos subidos desde el panel admin.**

| Volume | Path en contenedor | Contenido |
|--------|-------------------|-----------|
| `photo_data` | `/app/data/photos` | Fotos de operadores (registro de personal) |
| `content_data` | `/app/data/static` | Imágenes de la home: servicios, galería, noticias, hero, escenarios |
| `rut_data` | `/app/data/rut` | PDFs de RUT de operadores (registro de proveedores) |
| `postgres_data` | `/var/lib/postgresql/data` | Base de datos PostgreSQL |

### Migración de imágenes existentes (recuperación)

Si tienes un contenedor backend corriendo con imágenes que aún NO están en el
nuevo volume `content_data`, hay que copiarlas ANTES de recrear el contenedor:

```bash
# 1. En la VPS, copiar imágenes del contenedor viejo al volume nuevo:
docker cp logistica_backend:/app/data/static/content/. /tmp/content_backup/

# 2. Hacer el deploy con los nuevos volumes:
cd /home/server/Logistica
git pull origin master
docker compose -f docker-compose.prod.yml up -d --build

# 3. Copiar las imágenes al volume ya montado:
docker cp /tmp/content_backup/. logistica_backend:/app/data/static/content/
```

### Listar archivos en cada volume
```bash
# Imágenes de contenido (servicios, galería, noticias)
docker exec logistica_backend ls -la /app/data/static/content/

# Fotos de operadores
docker exec logistica_backend ls /app/data/photos/ | head -20

# PDFs de RUT
docker exec logistica_backend ls /app/data/rut/ | head -20
```

---

  ## ☁️ CLOUDFLARE (CDN + Protección)

  El dominio `ayceventos.com.co` está detrás de **Cloudflare** (proxy naranja).
  Esto significa que Cloudflare está entre los usuarios y tu VPS.

  ### Configuración SSL/TLS
  - Modo recomendado: **Full (strict)** — requiere certificado válido en el VPS (ver sección de certificados abajo).
  - Transición: empezar en **Full**, migrar a **Full (strict)** tras configurar DNS-01.
  - **NUNCA usar Flexible** (causa loop de redirecciones con Nginx).

  ### IPs reales de clientes (auditoría + rate-limit)
  - Nginx está configurado con `set_real_ip_from` para los rangos IP de Cloudflare
    y `real_ip_header CF-Connecting-IP` para resolver la IP real del cliente.
  - Nginx sobrescribe el header `X-Real-IP` con la IP saneada antes de reenviar
    al backend. El backend lee `X-Real-IP` (no forjable por el cliente) en
    `app/dependencies/rate_limit.py`. Esto evita bypass del rate-limit por
    spoofing de headers.
  - Para actualizar los rangos IP de Cloudflare (cambian ocasionalmente):
    ```bash
    # En el VPS, actualizar nginx.conf con las IPs actuales:
    curl -s https://www.cloudflare.com/ips-v4 | awk '{print "set_real_ip_from "$1";"}'
    curl -s https://www.cloudflare.com/ips-v6 | awk '{print "set_real_ip_from "$1";"}'
    ```
    Reemplazar el bloque en `nginx/nginx.conf` y reiniciar nginx:
    ```bash
    docker restart logistica_nginx
    ```

  ### ⚠️ Renovación de certificados Let's Encrypt — DNS-01 (recomendado)

  El proyecto incluye un certbot con el plugin `certbot-dns-cloudflare` que renueva
  los certificados vía **DNS-01 challenge** (no requiere pausar Cloudflare ni abrir puertos).

  **Setup inicial (una sola vez):**

  1. Crear un API Token en Cloudflare:
     - Ir a https://dash.cloudflare.com/profile/api-tokens
     - "Create Token" → plantilla "Edit zone DNS"
     - Zone Resource: `ayceventos.com.co`

  2. En el VPS, crear el archivo de credenciales:
     ```bash
     sudo cp certbot/cloudflare.ini.example /etc/letsencrypt/cloudflare.ini
     sudo nano /etc/letsencrypt/cloudflare.ini
     # Pegar el token de Cloudflare
     sudo chmod 600 /etc/letsencrypt/cloudflare.ini
     ```

  3. Obtener certificado inicial con DNS-01:
     ```bash
     cd /home/server/Logistica
     bash certbot/obtain-cert.sh
     ```

  4. Reconstruir el servicio certbot (para que use el plugin):
     ```bash
     docker compose -f docker-compose.prod.yml up -d --build certbot
     ```

  **Renovación:** automática cada 12h vía DNS-01 (no interrumpe el servicio).

  ### SSL/TLS Mode: Full (strict)
  Después de obtener el certificado con DNS-01, cambiar en Cloudflare:
  - SSL/TLS → Overview → **Full (strict)**

  Esto garantiza cifrado end-to-end (usuario → Cloudflare → VPS) sin posibilidad de downgrade.

  ---

  ## 🔐 GESTIÓN DE USUARIOS ADMIN

### Cambiar contraseña del superadmin
```bash
docker exec -it logistica_backend python -m scripts.reset_password
```

### Crear un nuevo admin desde la web
1. Entrar como superadmin (`00000000` / `Admin123!`)
2. Ir a **Administración → Superadmin → Crear Admin**

---

## 🌐 CERTIFICADOS SSL

### Verificar expiración
```bash
docker exec logistica_certbot certbot certificates
```
Renueva automáticamente cada 12h. Válidos por 90 días.

### Renovar manualmente (si algo falla)
```bash
docker stop logistica_nginx
docker exec logistica_certbot certbot renew
docker start logistica_nginx
```

---

## ⚠️ EMERGENCIAS

### El VPS se reinició (corte de luz, mantenimiento)
```bash
cd /home/server/Logistica
docker compose -f docker-compose.prod.yml up -d
```
Todo debería arrancar solo. Si no, verificar con `ps`.

### La web está caída completamente
```bash
# 1. Ver qué contenedores están parados
docker compose -f docker-compose.prod.yml ps

# 2. Levantar todo
docker compose -f docker-compose.prod.yml up -d

# 3. Si el backend no arranca, ver logs
docker logs logistica_backend --tail 50
```

### Rollback urgente (volver a versión anterior)
```bash
cd /home/server/Logistica

# Ver últimos commits
git log --oneline -10

# Volver a un commit anterior
git checkout <commit-hash>

# Rebuild
docker compose -f docker-compose.prod.yml up -d --build
```

### Reset completo (¡PELIGRO! Borra todos los datos)
```bash
cd /home/server/Logistica
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d --build
```
⚠️ **Esto borra la DB y todas las fotos. Solo usar en desastre total.**

---

## 📊 COMANDOS RÁPIDOS (Cheat Sheet)

| Acción | Comando |
|--------|---------|
| Ver estado | `docker compose -f docker-compose.prod.yml ps` |
| Reiniciar backend | `docker restart logistica_backend` |
| Reiniciar todo | `docker compose -f docker-compose.prod.yml restart` |
| Ver logs backend | `docker logs logistica_backend --tail 50` |
| Backup DB | `bash scripts/backup.sh` (manual) o automático vía cron |
| Restaurar backup | `bash scripts/restore_backup.sh <fecha>` |
| Actualizar (deploy) | `git pull && docker compose -f docker-compose.prod.yml up -d --build` |
| Espacio en disco | `docker system df` |
| Limpiar imágenes viejas | `docker image prune -f` |

---

## 📞 CUÁNDO PEDIR AYUDA

- Si después de reiniciar el backend no vuelve a estar `healthy` en 2 minutos → revisar logs
- Si la DB está corrupta → restaurar backup
- Si SSL expira → renovar manualmente
- Si el disco se llena → `docker system prune -f` y borrar backups viejos