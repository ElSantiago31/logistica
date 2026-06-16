# 📖 Runbook VPS — Guía de Operaciones

> Comandos para gestionar el servidor de producción (`ayceventos.com.co`).
> Todos los comandos se ejecutan por **SSH en la VPS**, dentro de `/opt/logistica`.

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
cd /opt/logistica
git pull origin master
docker compose -f docker-compose.prod.yml up -d --build
```

### Cambios con migraciones nuevas
```bash
cd /opt/logistica
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

## 💾 BACKUP DE BASE DE DATOS

### Backup completo (antes de cambios importantes)
```bash
docker exec logistica_postgres pg_dump -U logistica_user logistica_db > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restaurar un backup
```bash
cat backup_20260616.sql | docker exec -i logistica_postgres psql -U logistica_user logistica_db
```

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
cd /opt/logistica
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
cd /opt/logistica

# Ver últimos commits
git log --oneline -10

# Volver a un commit anterior
git checkout <commit-hash>

# Rebuild
docker compose -f docker-compose.prod.yml up -d --build
```

### Reset completo (¡PELIGRO! Borra todos los datos)
```bash
cd /opt/logistica
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
| Backup DB | `docker exec logistica_postgres pg_dump -U logistica_user logistica_db > backup.sql` |
| Actualizar (deploy) | `git pull && docker compose -f docker-compose.prod.yml up -d --build` |
| Espacio en disco | `docker system df` |
| Limpiar imágenes viejas | `docker image prune -f` |

---

## 📞 CUÁNDO PEDIR AYUDA

- Si después de reiniciar el backend no vuelve a estar `healthy` en 2 minutos → revisar logs
- Si la DB está corrupta → restaurar backup
- Si SSL expira → renovar manualmente
- Si el disco se llena → `docker system prune -f` y borrar backups viejos