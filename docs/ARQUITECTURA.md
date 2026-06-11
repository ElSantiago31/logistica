# Arquitectura General — A&C Logística

> Documentación del sistema de gestión logística para producción de eventos.
> Última actualización: Junio 2026

---

## 1. Visión General

**A&C Logística** es un sistema web para gestionar personal auxiliar en eventos (logística, montaje, operación). Permite enrolar operadores, asignarlos a eventos, hacer check-in con escáner QR/PDF417, registrar asistencia offline (PWA), enviar invitaciones por WhatsApp y calcular nómina.

### Stack Tecnológico

| Componente | Tecnología | Versión |
|---|---|---|
| **Backend** | FastAPI (Python) | 0.111.0 |
| **Servidor ASGI** | Uvicorn | 0.30.1 |
| **Base de datos** | PostgreSQL | 16 (Alpine) |
| **ORM** | SQLAlchemy (async) | 2.0.31 |
| **Driver DB** | asyncpg | 0.29.0 |
| **Migraciones** | Alembic | 1.13.1 |
| **Autenticación** | JWT (python-jose) | 3.3.0 |
| **Hash contraseñas** | passlib + bcrypt | 1.7.4 / 4.1.3 |
| **WhatsApp API** | Zenvia (httpx) | 0.27.0 |
| **Procesamiento imágenes** | Pillow | 10.4.0 |
| **Rate Limiting** | slowapi | 0.1.9 |
| **Templates HTML** | Jinja2 (integrado FastAPI) | — |
| **Frontend CSS** | Tailwind CSS (CDN) | — |
| **Frontend JS** | Vanilla JS + HTMX | 1.9.12 |
| **PWA IndexedDB** | Dexie.js | 3.2.7 |
| **Escáner QR** | html5-qrcode | 2.3.8 |
| **Proxy inverso** | Nginx (Alpine) | — |
| **SSL/TLS** | Let's Encrypt (certbot) | — |
| **Contenedores** | Docker Compose | 3.9 |

---

## 2. Arquitectura de Despliegue

### Desarrollo (`docker-compose.yml`)

```
┌─────────────────┐     ┌──────────────────┐
│  FastAPI :8000   │────▶│  PostgreSQL :5432 │
│  (local)         │     │  (contenedor)     │
└─────────────────┘     └──────────────────┘
                              │
                        ┌─────┴──────┐
                        │ pgAdmin     │
                        │ :5050       │
                        └────────────┘
```

- Solo servicios: `postgres` + `pgadmin`
- Backend se ejecuta localmente con `uvicorn`
- Base de datos expuesta en puerto 5432

### Producción (`docker-compose.prod.yml`)

```
Internet
   │
   ▼
┌──────────────────────────────────┐
│  Nginx :80/:443                  │
│  ┌─────────────────────────────┐ │
│  │ SSL (Let's Encrypt)         │ │
│  │ Proxy reverso → backend     │ │
│  │ Archivos estáticos (fotos)  │ │
│  └─────────────────────────────┘ │
└──────────────┬───────────────────┘
               │ (red interna Docker)
               ▼
┌──────────────────────────────────┐
│  FastAPI backend :8000           │
│  ┌─────────────────────────────┐ │
│  │ API REST (/api/*)           │ │
│  │ Templates Jinja2            │ │
│  │ Static files (JS, CSS)      │ │
│  └─────────────────────────────┘ │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  PostgreSQL :5432                │
│  (sin exposición externa)        │
└──────────────────────────────────┘

┌──────────────────────────────────┐
│  Certbot (renovación auto SSL)   │
└──────────────────────────────────┘
```

- Todos los servicios en red interna Docker (`internal`)
- Solo Nginx expone puertos (80/443)
- Dominio: `ayceventos.com.co`
- Fotos servidas directamente por Nginx (`/data/photos/`)
- Certbot renueva certificados automáticamente cada 12h

---

## 3. Estructura del Proyecto

```
logistica/
├── .env.example              # Variables de entorno de ejemplo
├── .gitignore
├── docker-compose.yml        # Desarrollo (postgres + pgadmin)
├── docker-compose.prod.yml   # Producción (full stack)
├── deploy.sh                 # Script de despliegue
│
├── backend/
│   ├── Dockerfile            # Imagen Docker del backend
│   ├── .dockerignore
│   ├── alembic.ini           # Configuración de migraciones
│   ├── pytest.ini            # Config de tests
│   ├── requirements.txt      # Dependencias Python
│   ├── run_server.py         # Entry point del servidor
│   │
│   ├── alembic/
│   │   ├── env.py            # Config async de Alembic
│   │   └── versions/         # Migraciones de BD
│   │       ├── 64953d96e4b9_initial_schema.py
│   │       ├── 4324281308a3_add_operator_experience_sizes.py
│   │       ├── add_education_level.py
│   │       └── add_experience_roles.py
│   │
│   ├── app/
│   │   ├── main.py           # App FastAPI, rutas HTML, middleware
│   │   ├── config.py         # Settings (Pydantic BaseSettings)
│   │   ├── database.py       # Engine/session async SQLAlchemy
│   │   │
│   │   ├── models/           # Modelos SQLAlchemy (ORM)
│   │   │   ├── users.py
│   │   │   ├── operators.py
│   │   │   ├── events.py
│   │   │   ├── sync.py
│   │   │   └── roles.py
│   │   │
│   │   ├── schemas/          # Esquemas Pydantic (validación)
│   │   │   ├── auth.py
│   │   │   ├── operators.py
│   │   │   └── events.py
│   │   │
│   │   ├── routers/          # Endpoints API REST
│   │   │   ├── auth.py       # Login, registro, tokens
│   │   │   ├── operators.py  # CRUD operadores
│   │   │   ├── events.py     # CRUD eventos + asignaciones
│   │   │   ├── catalogs.py   # EPS, ARL (catálogos)
│   │   │   ├── whatsapp.py   # Webhook + envío WhatsApp
│   │   │   ├── sync.py       # Descarga offline + sync asistencia
│   │   │   ├── payroll.py    # Nómina
│   │   │   └── reports.py    # Reportes
│   │   │
│   │   ├── services/         # Lógica de negocio
│   │   │   ├── auth.py       # JWT, hash, verificación
│   │   │   ├── operators.py  # Gestión operadores
│   │   │   ├── events.py     # Gestión eventos
│   │   │   └── whatsapp.py   # Integración Zenvia
│   │   │
│   │   ├── dependencies/     # Dependencias FastAPI
│   │   │   ├── auth.py       # get_current_user, require_roles
│   │   │   └── rate_limit.py # SlowAPI limiter
│   │   │
│   │   └── templates/        # Plantillas Jinja2
│   │       ├── base.html
│   │       ├── landing/      # Páginas públicas
│   │       └── admin/        # Panel administración
│   │
│   ├── scripts/              # Scripts utilitarios
│   │   ├── seed_roles.py
│   │   ├── reminders_cron.py
│   │   └── ...
│   │
│   └── tests/                # Tests automatizados
│
├── frontend/
│   ├── js/                   # JavaScript de la PWA
│   │   ├── db.js             # IndexedDB wrapper (Dexie)
│   │   ├── scanner.js        # Escáner QR/PDF417
│   │   ├── signature.js      # Firmas digitales
│   │   └── sync.js           # Sincronización offline
│   │
│   └── public/               # Archivos estáticos públicos
│       ├── manifest.json     # PWA manifest
│       └── sw.js             # Service Worker
│
├── nginx/
│   └── nginx.conf            # Proxy reverso producción
│
├── logo/
│   └── logo.jpeg
│
└── docs/                     # Documentación
```

---

## 4. Flujo de la Aplicación

### 4.1 Autenticación

```
Operador/Admin → Login (documento + contraseña)
       │
       ▼
POST /api/auth/login
       │
       ├── Verifica documento + password hash
       ├── Genera access_token (JWT, 15 min)
       ├── Genera refresh_token (JWT, 7 días)
       └── Retorna tokens + datos usuario
       
Token JWT incluye:
  - sub: user_id (UUID)
  - type: "access" | "refresh"
  - jti: ID único para revocación
  - exp: expiración
```

### 4.2 Roles y Permisos

| Rol | Permisos |
|---|---|
| `superadmin` | Acceso total, gestión usuarios, configuración |
| `coordinator` | Gestión eventos, asignaciones, check-in, nómina |
| `operator` | Ver su perfil, actualizar datos, ver sus asignaciones |

### 4.3 Flujo de Evento

```
1. Coordinador crea evento (draft)
2. Define necesidades de personal (roles + cantidades)
3. Asigna operadores a roles
4. Publica evento → se envían invitaciones WhatsApp
5. Operadores confirman/rechazan via WhatsApp
6. Día del evento → Check-in (QR escáner o búsqueda manual)
7. Post-evento → Registro de horas, cálculo nómina
8. Firma digital del operador confirmando pago
```

### 4.4 Funcionamiento Offline (PWA)

```
Online:
  → Descargar datos del evento → IndexedDB (Dexie)
  → Operadores, asignaciones, datos del evento

Offline:
  → Búsqueda local en IndexedDB
  → Check-in se guarda en tabla attendance (sync_status: pending)
  → UI muestra "📴 Guardado offline"

Al recuperar conexión:
  → Evento 'online' dispara syncPendingRecords()
  → POST /api/sync/attendance con registros pendientes
  → Se eliminan de la cola local
  → Se actualizan contadores
```

---

## 5. Configuración — Variables de Entorno

Archivo `.env` (ver `.env.example`):

| Variable | Default | Descripción |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | Host de PostgreSQL |
| `POSTGRES_PORT` | `5432` | Puerto de PostgreSQL |
| `POSTGRES_DB` | `logistica` | Nombre de la base de datos |
| `POSTGRES_USER` | `logistica` | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | `logistica_dev_2024` | Contraseña PostgreSQL |
| `DATABASE_URL` | *(auto)* | URL completa (sobreescribe individual) |
| `JWT_SECRET_KEY` | `change-me-in-production` | Clave secreta JWT |
| `JWT_ALGORITHM` | `HS256` | Algoritmo JWT |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Expiración access token |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Expiración refresh token |
| `ZENVIA_API_KEY` | `""` | API key de Zenvia (WhatsApp) |
| `ZENVIA_API_URL` | `https://api.zenvia.com/v2` | URL API Zenvia |
| `ZENVIA_CHANNEL_ID` | `""` | Canal Zenvia |
| `ZENVIA_WEBHOOK_TOKEN` | `""` | Token validación webhook |
| `APP_NAME` | `Logistica` | Nombre de la aplicación |
| `APP_VERSION` | `1.0.0` | Versión |
| `DEBUG` | `True` | Modo debug (desactiva Swagger en prod) |
| `ALLOWED_ORIGINS` | `http://localhost:8000` | Orígenes CORS (separados por coma) |
| `PHOTOS_DIR` | `./data/photos` | Directorio de fotos |
| `PHOTO_MAX_SIZE_MB` | `5` | Tamaño máximo de foto |

---

## 6. Endpoints Principales

| Prefijo | Router | Descripción |
|---|---|---|
| `/api/auth/*` | `auth.py` | Login, registro, refresh, logout |
| `/api/operators/*` | `operators.py` | CRUD operadores |
| `/api/events/*` | `events.py` | CRUD eventos + asignaciones |
| `/api/catalogs/*` | `catalogs.py` | EPS, ARL (catálogos) |
| `/api/whatsapp/*` | `whatsapp.py` | Envío + webhook WhatsApp |
| `/api/sync/*` | `sync.py` | Datos offline + sync asistencia |
| `/api/payroll/*` | `payroll.py` | Nómina y firmas |
| `/api/reports/*` | `reports.py` | Reportes y exportaciones |
| `/health` | `main.py` | Health check |

### Rutas HTML (Jinja2 Templates)

| Ruta | Template | Descripción |
|---|---|---|
| `/` | `landing/home.html` | Landing page empresa |
| `/enrolamiento` | `landing/index.html` | Formulario registro operador |
| `/enrolamiento/success` | `landing/success.html` | Registro exitoso |
| `/enrolamiento/login` | `landing/operator_login.html` | Login operador |
| `/enrolamiento/perfil` | `landing/operator_profile.html` | Perfil operador |
| `/admin` | `admin/index.html` | Dashboard admin |
| `/admin/login` | `admin/login.html` | Login admin |
| `/admin/operators` | `admin/operators.html` | Lista operadores |
| `/admin/events` | `admin/events.html` | Lista eventos |
| `/admin/events/create` | `admin/event_create.html` | Crear evento |
| `/admin/events/{id}` | `admin/event_detail.html` | Detalle evento |
| `/admin/events/{id}/checkin` | `admin/checkin.html` | Check-in (PWA) |
| `/admin/events/{id}/payroll` | `admin/payroll.html` | Nómina evento |

---

## 7. Seguridad

- **JWT** con access tokens (15 min) y refresh tokens (7 días)
- **Revocación de tokens** via tabla `revoked_tokens`
- **Rate limiting** con slowapi (protección contra abuso)
- **Headers de seguridad**: X-Content-Type-Options, X-Frame-Options, HSTS, XSS-Protection
- **CORS** configurado por orígen
- **SSL/TLS** obligatorio en producción
- **Passwords** hasheados con bcrypt
- **Fotos** con validación de tamaño máximo (5MB)
- **Permissions-Policy**: cámara habilitada (para escáner), geolocalización habilitada

---

## 8. Integraciones Externas

### Zenvia (WhatsApp Business API)

- **Envío de mensajes**: Plantillas para invitaciones, recordatorios (5 días, 1 día)
- **Webhook entrante**: Recibe confirmaciones/rechazos de operadores
- **Palabras clave**: El operador responde "CONFIRMAR"/"RECHAZAR" y el sistema actualiza el estado
- **Cola de salida**: Tabla `whatsapp_outbound_queue` con reintentos automáticos

---

## 9. Comentarios de Desarrollo y Decisiones Técnicas

### Base de datos
- Se usa **asyncpg** (no psycopg2) para aprovechar async/await en toda la aplicación
- **Alembic** con soporte async configurado en `alembic/env.py`
- La URL de BD se construye automáticamente desde componentes individuales o se sobreescribe con `DATABASE_URL`
- Todas las tablas tienen campos estándar: `id` (UUID), `created_at`, `updated_at`, `is_active`

### Frontend
- **No hay framework SPA** (no React/Vue) — se usa Jinja2 + HTMX + Vanilla JS
- **Tailwind CSS desde CDN** — no hay build step
- **Dexie.js** para IndexedDB — el check-in usa una instancia inline para evitar conflictos con `db.js`
- El escáner carga `html5-qrcode` dinámicamente desde CDN

### Offline/PWA
- Los datos se descargan antes del evento y se almacenan en IndexedDB
- Los check-ins offline se guardan localmente con `sync_status: pending`
- Al recuperar conexión, se sincronizan automáticamente
- El backend actualiza `assignment.status = "checked_in"` al recibir registros sincronizados

### Producción
- Nginx sirve fotos directamente con caché de 30 días
- El webhook de WhatsApp tiene timeout de 300s (vs 120s normal)
- Los docs de Swagger (`/docs`, `/redoc`) se desactivan en producción (`DEBUG=False`)