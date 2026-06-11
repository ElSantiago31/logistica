# Guía de Desarrollo — AyC Eventos

> Convenciones, estructura y flujo de trabajo para desarrolladores.
> Última actualización: Junio 2026

---

## 1. Stack Tecnológico

### Backend
| Librería | Versión | Propósito |
|---|---|---|
| FastAPI | 0.111.0 | Framework web async |
| Uvicorn | 0.30.1 | Servidor ASGI |
| SQLAlchemy | 2.0.31 | ORM async (con asyncpg) |
| asyncpg | 0.29.0 | Driver PostgreSQL async |
| Alembic | 1.13.1 | Migraciones de BD |
| python-jose | 3.3.0 | JWT tokens |
| passlib + bcrypt | 1.7.4 / 4.1.3 | Hash de contraseñas |
| pydantic-settings | 2.3.4 | Configuración (Settings) |
| httpx | 0.27.0 | Cliente HTTP async (Zenvia) |
| Pillow | 10.4.0 | Procesamiento de imágenes |
| slowapi | 0.1.9 | Rate limiting |
| python-multipart | 0.0.9 | Upload de archivos |

### Testing
| Librería | Propósito |
|---|---|
| pytest | Framework de testing |
| pytest-asyncio | Soporte async en tests |
| pytest-cov | Coverage |
| httpx | Cliente para testear API |

### Frontend
| Librería | Propósito |
|---|---|
| Tailwind CSS (CDN) | Framework CSS |
| HTMX 1.9.12 (CDN) | Interactividad |
| Dexie.js 3.2.7 (CDN) | IndexedDB wrapper |
| html5-qrcode 2.3.8 (CDN) | Escáner QR/PDF417 |

---

## 2. Estructura del Proyecto

```
logistica/
├── .env.example              # Template de variables de entorno
├── .gitignore
├── deploy.sh                 # Script de despliegue producción
├── docker-compose.yml        # Desarrollo local
├── docker-compose.prod.yml   # Producción
├── nginx/
│   └── nginx.conf            # Configuración Nginx
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── pytest.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/         # Migraciones
│   ├── app/
│   │   ├── main.py           # App FastAPI (entrada)
│   │   ├── config.py         # Settings (Pydantic BaseSettings)
│   │   ├── database.py       # Sesión async de SQLAlchemy
│   │   ├── models/           # Modelos ORM
│   │   ├── schemas/          # Schemas Pydantic (validación)
│   │   ├── routers/          # Endpoints (controllers)
│   │   ├── services/         # Lógica de negocio
│   │   ├── dependencies/     # Dependencias inyectables
│   │   └── templates/        # Templates Jinja2
│   ├── scripts/              # Scripts de utilidad
│   └── tests/                # Tests
├── frontend/
│   ├── js/                   # JavaScript modules
│   └── public/               # Archivos estáticos PWA
├── logo/
└── docs/                     # Documentación
```

---

## 3. Convenciones de Código

### Python (Backend)

- **Async/await:** Todo es async (routers, services, database)
- **Tipado:** Usar type hints en todas las funciones
- **Imports:** Agrupar en orden: stdlib → third-party → local
- **Naming:**
  - Archivos: `snake_case.py`
  - Clases: `PascalCase`
  - Funciones/variables: `snake_case`
  - Constantes: `UPPER_SNAKE_CASE`
- **Docstrings:** Mínimo en funciones públicas de routers

### Estructura de un Router

```python
"""Brief description of the router."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/resource", tags=["ResourceName"])

@router.get("/")
async def list_resources(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all resources."""
    ...
```

### Estructura de un Modelo

```python
class MyModel(Base):
    __tablename__ = "my_table"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)
    # ... fields
```

### Templates Jinja2

- Extender `base.html` con `{% extends "base.html" %}`
- Usar los bloques: `{% block title %}`, `{% block content %}`, `{% block scripts %}`
- JS inline en `{% block scripts %}`, no archivos separados (excepto PWA modules)
- Tailwind para estilos, no CSS custom (excepto animaciones)

---

## 4. Flujo de Trabajo (Git)

### Branches
```
master        → Producción (deploy automatico)
├── develop   → Desarrollo activo
├── feature/* → Nuevas funcionalidades
├── fix/*     → Bug fixes
└── hotfix/*  → Fixes urgentes en producción
```

### Proceso
1. Crear branch desde `develop`: `git checkout -b feature/nombre`
2. Desarrollar + tests
3. Commit con mensaje descriptivo
4. Push + Pull Request a `develop`
5. Review + merge
6. Deploy: merge `develop` → `master` + ejecutar `deploy.sh`

---

## 5. Agregar una Nueva Funcionalidad

### Ejemplo: Nuevo endpoint + modelo

#### 1. Crear/Modificar Modelo
```python
# backend/app/models/mi_modelo.py
```

#### 2. Crear Migración
```bash
cd backend
alembic revision --autogenerate -m "add mi_tabla"
alembic upgrade head
```

#### 3. Crear Schema
```python
# backend/app/schemas/mi_schema.py
```

#### 4. Crear Router
```python
# backend/app/routers/mi_router.py
```

#### 5. Registrar en main.py
```python
from app.routers.mi_router import router as mi_router
app.include_router(mi_router)
```

#### 6. Crear Template (si requiere UI)
```html
<!-- backend/app/templates/admin/mi_pagina.html -->
{% extends "base.html" %}
{% block title %}Mi Página{% endblock %}
{% block content %}...{% endblock %}
```

#### 7. Agregar Ruta HTML en main.py
```python
@app.get("/admin/mi-pagina")
async def mi_pagina(request: Request):
    return templates.TemplateResponse("admin/mi_pagina.html", {"request": request})
```

#### 8. Tests
```python
# backend/tests/test_mi_router.py
```

---

## 6. Testing

### Ejecutar Tests

```bash
cd backend

# Todos los tests
pytest

# Con coverage
pytest --cov=app --cov-report=html

# Un archivo específico
pytest tests/test_auth.py -v

# Tests marcados
pytest -m "not slow"
```

### Estructura de Test

```python
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_login():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/auth/login", json={
            "document_number": "12345678",
            "password": "test123"
        })
        assert response.status_code in (200, 401)
```

---

## 7. Migraciones (Alembic)

```bash
# Crear migración automática (detecta cambios en modelos)
alembic revision --autogenerate -m "descripción"

# Aplicar todas las migraciones pendientes
alembic upgrade head

# Retroceder una migración
alembic downgrade -1

# Ver estado actual
alembic current

# Ver historial
alembic history
```

### Importante
- Siempre revisar el archivo generado antes de aplicar
- Las migraciones con datos (`op.execute`) requieren revision manual
- En producción: usar `docker compose exec backend alembic upgrade head`

---

## 8. Configuración (Settings)

La configuración se maneja con `pydantic-settings` en `app/config.py`:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    JWT_SECRET_KEY: str
    # ...

    class Config:
        env_file = ".env"

settings = Settings()
```

- Todas las variables se leen del `.env`
- Tipado estricto con valores default donde aplica
- Acceso global: `from app.config import settings`

---

## 9. Scripts de Utilidad

| Script | Propósito |
|---|---|
| `scripts/seed_roles.py` | Poblar roles de operadores |
| `scripts/add_education_level.py` | Agregar campo nivel educativo |
| `scripts/reminders_cron.py` | Envío programado de recordatorios WhatsApp |
| `scripts/check_columns.py` | Verificar columnas en BD |
| `scripts/test_operator.py` | Tests de operadores |

---

## 10. Documentación Generada

| Archivo | Contenido |
|---|---|
| `docs/ARQUITECTURA.md` | Arquitectura general del sistema |
| `docs/BACKEND_MODELOS.md` | Modelos de BD y relaciones |
| `docs/BACKEND_APIS.md` | Endpoints REST y servicios |
| `docs/BACKEND_VISTAS.md` | Templates y vistas HTML |
| `docs/FRONTEND_PWA.md` | PWA, JS offline, Service Worker |
| `docs/GUIA_DESPLIEGUE.md` | Despliegue producción y desarrollo |
| `docs/GUIA_DESARROLLO.md` | Esta guía — desarrollo |
| `docs/PLAN_MAESTRO.md` | Plan maestro del proyecto |
| `docs/SPRINT1_FASE1.md` | Reporte Sprint 1 |