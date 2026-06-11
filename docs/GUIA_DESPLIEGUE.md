# Guía de Despliegue — AyC Eventos

> Instrucciones para desplegar en producción (VPS) y desarrollo local.
> Última actualización: Junio 2026

---

## 1. Requisitos

| Componente | Versión | Nota |
|---|---|---|
| Docker | 20+ | Se instala via `deploy.sh` |
| Docker Compose | v2+ | Incluido con Docker |
| VPS | Ubuntu 22.04+ | Mínimo 2GB RAM, 20GB disco |
| Dominio | ayceventos.com.co | Apuntando al VPS |

---

## 2. Despliegue en Producción

### Script Automatizado (`deploy.sh`)

```bash
# En el VPS:
git clone https://github.com/ElSantiago31/logistica.git /opt/logistica
cd /opt/logistica
bash deploy.sh
```

### Pasos que ejecuta `deploy.sh`

1. **Instalar Docker** si no está presente
2. **Clonar repo** en `/opt/logistica`
3. **Pull** de última versión (`git pull origin master`)
4. **Crear `.env`** desde `.env.example` con secretos generados
5. **Certificado SSL** con Let's Encrypt (certbot)
6. **Build + Start** de contenedores Docker
7. **Migraciones** (`alembic upgrade head`)
8. **Seed** de datos iniciales

### Post-despliegue

- Editar `.env` para agregar credenciales Zenvia (WhatsApp)
- Reiniciar: `docker compose -f docker-compose.prod.yml restart backend`

---

## 3. Variables de Entorno (`.env`)

### Base de Datos
| Variable | Ejemplo | Descripción |
|---|---|---|
| `POSTGRES_HOST` | `localhost` (dev) / `postgres` (prod) | Host PostgreSQL |
| `POSTGRES_PORT` | `5432` | Puerto |
| `POSTGRES_DB` | `logistica` | Nombre BD |
| `POSTGRES_USER` | `logistica` | Usuario |
| `POSTGRES_PASSWORD` | *(generado)* | Contraseña |
| `DATABASE_URL` | `postgresql+asyncpg://...` | URL completa |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://..._test` | BD de pruebas |

### JWT
| Variable | Default | Descripción |
|---|---|---|
| `JWT_SECRET_KEY` | *(generado)* | Clave secreta para firmar tokens |
| `JWT_ALGORITHM` | `HS256` | Algoritmo |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Expiración access token |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Expiración refresh token |

### WhatsApp (Zenvia)
| Variable | Descripción |
|---|---|
| `ZENVIA_API_KEY` | API key de Zenvia |
| `ZENVIA_API_URL` | `https://api.zenvia.com/v2` |
| `ZENVIA_CHANNEL_ID` | ID del canal WhatsApp |
| `ZENVIA_WEBHOOK_TOKEN` | Token para validar webhooks |
| `ZENVIA_TEMPLATE_INVITATION` | Nombre plantilla invitación |
| `ZENVIA_TEMPLATE_REMINDER_1D` | Plantilla recordatorio 1 día |
| `ZENVIA_TEMPLATE_REMINDER_5D` | Plantilla recordatorio 5 días |
| `ZENVIA_CONFIRM_KEYWORDS` | Palabras de confirmación |
| `ZENVIA_REJECT_KEYWORDS` | Palabras de rechazo |

### App
| Variable | Default | Descripción |
|---|---|---|
| `APP_NAME` | `AyC Eventos` | Nombre |
| `APP_VERSION` | `1.0.0` | Versión |
| `DEBUG` | `false` | Modo debug |
| `ALLOWED_ORIGINS` | `https://ayceventos.com.co` | CORS |

### Fotos
| Variable | Default | Descripción |
|---|---|---|
| `PHOTOS_DIR` | `./data/photos` | Directorio fotos |
| `PHOTOS_THUMBNAIL_DIR` | `./data/photos/thumbnails` | Thumbnails |
| `PHOTO_MAX_SIZE_MB` | `5` | Tamaño máximo |

---

## 4. Arquitectura Docker (Producción)

```
docker-compose.prod.yml
├── postgres      → BD PostgreSQL 16 Alpine (puerto interno 5432)
├── backend       → FastAPI app (puerto interno 8000)
├── nginx         → Reverse proxy (80, 443) + SSL + archivos estáticos
└── certbot       → Renovación automática SSL (cada 12h)

Volumes:
├── postgres_data  → Datos PostgreSQL (persistente)
├── photo_data     → Fotos operadores (persistente)
├── certbot_data   → Certificados SSL
└── certbot_www    → Challenge ACME

Network: internal (sin exposición directa excepto nginx)
```

### Puertos Expuestos
- **80** → HTTP (redirect a HTTPS)
- **443** → HTTPS (nginx → backend)
- El backend **no** se expone directamente

---

## 5. Desarrollo Local

### Opción A: Docker Compose (desarrollo)

```bash
# Levantar servicios
docker compose up -d

# Migraciones
docker compose exec backend alembic upgrade head

# Seed
docker compose exec backend python -m scripts.seed

# Ver logs
docker compose logs -f backend
```

### Opción B: Local sin Docker

```bash
# 1. PostgreSQL corriendo localmente
# 2. Crear .env con POSTGRES_HOST=localhost

# 3. Crear virtualenv
cd backend
python -m venv venv
source venv/bin/activate  # Linux
# venv\Scripts\activate   # Windows

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Migraciones
alembic upgrade head

# 6. Ejecutar
uvicorn app.main:app --reload --port 8000
```

---

## 6. Comandos Útiles (Producción)

```bash
# Ver estado de contenedores
docker compose -f docker-compose.prod.yml ps

# Ver logs del backend
docker compose -f docker-compose.prod.yml logs -f backend

# Reiniciar backend
docker compose -f docker-compose.prod.yml restart backend

# Ejecutar migración
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head

# Crear nueva migración
docker compose -f docker-compose.prod.yml exec backend alembic revision --autogenerate -m "description"

# Bash en el contenedor
docker compose -f docker-compose.prod.yml exec backend bash

# Acceder a PostgreSQL
docker compose -f docker-compose.prod.yml exec postgres psql -U logistica

# Backup BD
docker compose -f docker-compose.prod.yml exec postgres pg_dump -U logistica logistica > backup.sql

# Renovar SSL manualmente
docker compose -f docker-compose.prod.yml exec certbot certbot renew
```

---

## 7. SSL / HTTPS

- **Proveedor:** Let's Encrypt (gratuito)
- **Dominio:** `ayceventos.com.co` + `www.ayceventos.com.co`
- **Renovación:** Automática cada 12 horas (contenedor certbot)
- **Certificados:** `/etc/letsencrypt/live/ayceventos.com.co/`

### Nginx config
- Redirige HTTP → HTTPS
- Proxy pass a backend (`http://backend:8000`)
- Sirve fotos desde `/data/photos/`
- Sirve estáticos desde `/static/frontend/`

---

## 8. Monitoreo y Troubleshooting

### Health Check
```bash
curl https://ayceventos.com.co/api/auth/me  # 401 = OK (servidor responde)
```

### Problemas Comunes

| Problema | Solución |
|---|---|
| 502 Bad Gateway | Backend no listo, esperar o reiniciar |
| SSL expirado | `docker compose exec certbot certbot renew` |
| Migración pendiente | `docker compose exec backend alembic upgrade head` |
| Fotos no cargan | Verificar volume `photo_data` montado en nginx |
| WhatsApp no envía | Verificar credenciales Zenvia en `.env` |