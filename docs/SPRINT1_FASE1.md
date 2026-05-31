# SPRINT 1 — FASE 1.1: Proyecto + Docker + FastAPI Skeleton

## Estado: ✅ COMPLETADA

**Fecha:** Día 1
**Commit:** `b28d28a` — FASE 1.1: Proyecto scaffolding + Docker + FastAPI base

---

## Lo que se completó

### Infraestructura
- [x] Repositorio Git inicializado con `.gitignore` configurado
- [x] `docker-compose.yml` con PostgreSQL 16 + pgAdmin
- [x] Variables de entorno (`.env` + `.env.example`)

### Backend
- [x] FastAPI app base (`app/main.py`) con:
  - Health check endpoint (`/health`)
  - Root endpoint (`/`)
  - CORS configurado (orígenes desde `.env`)
  - Security headers middleware (X-Content-Type-Options, X-Frame-Options, etc.)
  - Startup event (crea directorios de fotos)
- [x] Settings (`app/config.py`) con pydantic-settings:
  - Database, JWT, WhatsApp, App, Photos settings
  - Properties computadas: `effective_database_url`, `allowed_origins_list`
- [x] Database (`app/database.py`):
  - SQLAlchemy async engine + async_sessionmaker
  - `Base` declarativa para modelos
  - `get_db()` dependency para inyección
  - `get_test_db()` para tests
- [x] Estructura de paquetes completa:
  - `app/models/`, `app/schemas/`, `app/routers/`
  - `app/services/`, `app/dependencies/`, `app/middleware/`
  - `tests/`, `scripts/`

### Frontend (skeleton)
- [x] Directorios creados: `landing/`, `admin/`, `events/`, `pwa/`, `js/`

---

## Archivos Creados

```
logistica/
├── .gitignore
├── .env.example
├── docker-compose.yml
├── docs/
│   ├── PLAN_MAESTRO.md
│   └── SPRINT1_FASE1.md          ← este archivo
├── backend/
│   ├── .env
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/__init__.py
│   │   ├── schemas/__init__.py
│   │   ├── routers/__init__.py
│   │   ├── services/__init__.py
│   │   ├── dependencies/__init__.py
│   │   └── middleware/__init__.py
│   └── tests/__init__.py
└── frontend/
    └── public/
        ├── landing/
        ├── admin/
        ├── events/
        └── pwa/
```

---

## Cómo verificar

### 1. Levantar PostgreSQL
```bash
cd c:\proyectos\logistica
docker-compose up -d
```

### 2. Instalar dependencias
```bash
cd c:\proyectos\logistica\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Levantar FastAPI
```bash
cd c:\proyectos\logistica\backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Verificar endpoints
- http://localhost:8000/ → JSON con nombre y versión
- http://localhost:8000/health → `{"status": "healthy", ...}`
- http://localhost:8000/docs → Swagger UI

### 5. Verificar pgAdmin
- http://localhost:5050 → Login con admin@logistica.com / admin123

---

## Configuración actual (desarrollo)

| Parámetro | Valor |
|-----------|-------|
| DB Host | localhost:5432 |
| DB Name | logistica |
| DB User | logistica |
| DB Password | logistica_dev_2024 |
| JWT Secret | change-me-in-production... |
| Debug | true |
| CORS Origins | localhost:3000, localhost:8000 |

---

## ⚠️ Notas importantes

1. **El archivo `.env` NO está en Git** (está en `.gitignore`). Solo se versiona `.env.example`.
2. **PostgreSQL no está levantado aún** — se levanta con `docker-compose up -d`.
3. **No hay modelos ni tablas todavía** — eso se hace en la FASE 1.3.
4. **No hay autenticación todavía** — eso se hace en la FASE 1.5.

---

## ➡️ Siguiente: FASE 1.2 — Pruebas de Infraestructura

**Objetivo:** Crear tests que verifiquen:
- Conexión a PostgreSQL
- Health check endpoint
- Configuración de settings
- FastAPI app levanta correctamente

**Archivos a crear:**
- `tests/conftest.py` — Fixtures (async client, DB test)
- `tests/test_health.py` — Health check
- `tests/test_config.py` — Settings
- `tests/test_database.py` — Conexión DB

**Para retomar:** Leer `docs/SPRINT1_FASE1.md` (este archivo) y `docs/PLAN_MAESTRO.md`