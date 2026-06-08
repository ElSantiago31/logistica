# FASE 3.0 — DOCUMENTO DE CONTEXTO (Sprint 3)

> **Instrucción para la IA:** Al iniciar cualquier fase del Sprint 3, lee este documento PRIMERO para obtener el contexto completo del estado del proyecto. Luego lee el documento de la fase específica en la que vas a trabajar.

---

## Estado del Proyecto

| Sprint | Historias | Estado |
|---|---|---|
| **S1** (Días 1-3) | HU01: Infra + DB + Auth JWT · HU02: Login seguro | ✅ Completado |
| **S2** (Días 4-6) | HU03: Registro operadores con foto · HU04: CRUD operadores | ✅ Completado |
| **S3** (Días 7-9) | HU05: Landing Page · HU06: Panel administración | 🔜 En progreso |

---

## Stack Tecnológico

| Componente | Tecnología |
|---|---|
| Backend | FastAPI (Python 3.11+) + Uvicorn |
| Base de Datos | PostgreSQL 16 + SQLAlchemy 2.0 async + asyncpg |
| Migraciones | Alembic (async) |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Frontend Admin | HTML + Tailwind CDN + HTMX + Vanilla JS |
| PWA | Service Worker + Dexie.js + html5-qrcode (futuro) |
| WhatsApp | Meta Business API + httpx (futuro) |
| Infra | Docker Compose (PostgreSQL + pgAdmin) |
| Testing | pytest + pytest-asyncio + httpx |

---

## Estructura de Base de Datos (16 Tablas)

```
Catálogos:     roles, eps, arl
Núcleo:        users, operators
Eventos:       events, event_staff_needs, event_assignments
WhatsApp:      whatsapp_outbound_queue
Offline/PWA:   sync_sessions, attendance_log
Nómina:        evaluations, payroll, signatures
Sistema:       audit_log, revoked_tokens
```

Todas usan UUID como PK, campos automáticos `created_at`, `updated_at`, `is_active`.

---

## Backend — Modelos (16/16 implementados)

Ubicación: `backend/app/models/`

| Modelo | Tabla | Campos clave |
|---|---|---|
| `Role` | `roles` | name, slug, description, base_rate |
| `EPS` | `eps` | name, code, nit |
| `ARL` | `arl` | name, code, nit |
| `User` | `users` | email, password_hash, first_name, last_name, phone, document_number, user_type (superadmin/coordinator/operator), role_id, is_verified, is_approved |
| `Operator` | `operators` | user_id (FK), eps_id, arl_id, photo_path, photo_thumbnail_path, birth_date, city, blood_type, emergency_contact_*, background_check_status, rating_avg, total_events |
| `Event` | `events` | name, slug, location, start_date, end_date, status (draft/published/in_progress/completed/cancelled), created_by |
| `EventStaffNeed` | `event_staff_needs` | event_id, role_id, quantity_needed, quantity_confirmed, rate_per_shift |
| `EventAssignment` | `event_assignments` | event_id, operator_id, role_id, status (invited/confirmed/rejected/standby/no_show/checked_in) |
| `WhatsAppOutboundQueue` | `whatsapp_outbound_queue` | event_id, phone_number, template_name, message_type, status |
| `SyncSession` | `sync_sessions` | event_id, session_type (download/upload), status, sync_token |
| `AttendanceLog` | `attendance_log` | event_id, operator_id, check_in_time, check_in_method (qr/pdf417/manual/nfc) |
| `Evaluation` | `evaluations` | event_id, operator_id, scores (punctuality/performance/appearance/attitude), overall_score |
| `Payroll` | `payroll` | event_id, operator_id, hours_worked, rate_per_hour, total_amount, status |
| `Signature` | `signatures` | payroll_id, operator_id, signature_data (Base64), signature_hash (SHA-256) |
| `AuditLog` | `audit_log` | user_id, action, resource_type, resource_id, details |
| `RevokedToken` | `revoked_tokens` | token_jti, user_id, revoked_at, reason |

---

## Backend — Routers Implementados

### Auth (`/api/auth`) — `backend/app/routers/auth.py`

| Endpoint | Método | Auth | Descripción |
|---|---|---|---|
| `/api/auth/login` | POST | Pública | Login con email+password, retorna access+refresh tokens |
| `/api/auth/register` | POST | Pública | Registro público de operadores (landing) |
| `/api/auth/refresh` | POST | Refresh Token | Renueva tokens |
| `/api/auth/logout/{jti}` | POST | JWT | Revoca token específico |
| `/api/auth/change-password` | POST | JWT | Cambio de contraseña |
| `/api/auth/me` | GET | JWT | Info del usuario actual |

### Operators (`/api/operators`) — `backend/app/routers/operators.py`

| Endpoint | Método | Auth | Descripción |
|---|---|---|---|
| `/api/operators/` | GET | Admin/Coordinator | Lista paginada de operadores |
| `/api/operators/{user_id}` | GET | JWT (self o admin) | Detalle de operador |
| `/api/operators/{user_id}` | PUT | JWT (self o admin) | Actualizar perfil |
| `/api/operators/{user_id}` | DELETE | Superadmin | Soft-delete |
| `/api/operators/{user_id}/photo` | POST | JWT (self o admin) | Subir foto (multipart) |

---

## Backend — Servicios Implementados

### `backend/app/services/auth.py`
- `hash_password(password)` → str
- `verify_password(plain, hashed)` → bool
- `create_access_token(user_id, email, user_type, role_name)` → dict
- `create_refresh_token(user_id, email)` → dict
- `decode_token(token)` → dict | None
- `is_token_revoked(db, jti)` → bool
- `revoke_token(db, jti, user_id, reason)` → None
- `authenticate_user(db, email, password)` → User | None

### `backend/app/services/operators.py`
- `get_operators(db, skip, limit, is_approved, is_active)` → (List[User], int)
- `get_operator(db, user_id)` → User | None
- `update_operator(db, user_id, update_data, is_admin)` → User | None
- `delete_operator(db, user_id)` → bool (soft delete)
- `upload_operator_photo(db, user_id, file)` → User | None

---

## Backend — Schemas Pydantic

### `backend/app/schemas/auth.py`
- `LoginRequest` (email, password)
- `LoginResponse` (access_token, refresh_token, token_type, expires_in, user: UserBrief)
- `UserBrief` (id, email, first_name, last_name, user_type, role_name)
- `RegisterRequest` (email, password, confirm_password, first_name, last_name, phone, document_type, document_number)
- `OperatorRegisterRequest` (extiende Register + eps_id, arl_id, birth_date, city, blood_type, emergency contacts)
- `RefreshTokenRequest` (refresh_token)
- `ChangePasswordRequest` (current_password, new_password, confirm_new_password)

### `backend/app/schemas/operators.py`
- `OperatorBase` (phone, city, address, blood_type, emergency_contact_*, eps_id, arl_id)
- `OperatorUpdateRequest` (extiende Base + first_name, last_name, birth_date)
- `OperatorAdminUpdateRequest` (extiende Update + is_verified, is_approved, background_check_status, role_id, notes, is_active)
- `OperatorResponse` (todos los campos de User + Operator flat)
- `OperatorListResponse` (items: List[OperatorResponse], total: int)

---

## Backend — Dependencias de Auth

### `backend/app/dependencies/auth.py`
- `get_current_user` — Extrae usuario del JWT Bearer token
- `get_current_active_user` — Verifica is_verified e is_approved
- `require_roles(*roles)` — Factory que verifica user_type
- `require_superadmin` = require_roles("superadmin")
- `require_coordinator` = require_roles("superadmin", "coordinator")
- `require_admin_or_coordinator` = require_roles("superadmin", "coordinator")
- `require_any_role` = require_roles("superadmin", "coordinator", "operator")

---

## Backend — Configuración

### `backend/app/config.py` — Settings (pydantic-settings)
Lee de `.env`. Properties: `allowed_origins_list`, `effective_database_url`, `effective_test_database_url`.

### `backend/app/database.py`
- Async engine con pool_size=10, max_overflow=20
- Test engine lazy (pool_size=5)
- `Base` declarativa
- `get_db()` dependency con commit/rollback automático
- `get_test_db()` para tests

### `backend/app/main.py`
- FastAPI con lifespan (crea dirs de fotos)
- CORS middleware
- Security headers middleware
- Routers: auth, operators
- Static files: `/static/photos` → `data/photos/`
- Endpoints: `/health`, `/`

---

## Frontend — Estado Actual

**Completamente vacío.** Solo existen los directorios:

```
frontend/
├── js/          ← vacío (dexie.js, scanner.js, sync.js, signature.js - futuro)
└── public/
    ├── admin/   ← vacío (Panel administración - FASE3.3)
    ├── events/  ← vacío (Gestión eventos - Sprint 4+)
    ├── landing/ ← vacío (Registro operadores - FASE3.2)
    └── pwa/     ← vacío (Acreditación offline - Sprint 6+)
```

---

## Datos de Seed

Script: `backend/scripts/seed.py`
- 8 Roles: Bouncer, Acomodador, Logístico, Coordinador de Piso, Coordinador General, Azafata/o, Técnico, Producción
- 8 EPS: Sanitas, Nueva EPS, Sura, Saludvida, Famisanar, Coomeva, Compensar, Medimás
- 7 ARL: Positiva, Colpatria, Bolívar, Sura, Equidad, Colmena, La Previsora
- Superadmin: `admin@logistica.com` / `Admin123!`

---

## Cómo Levantar el Proyecto

```bash
# 1. Levantar PostgreSQL
cd c:\Users\Karen\Downloads\logistica
docker-compose up -d

# 2. Instalar dependencias
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Seed (crea tablas + datos iniciales)
python -m scripts.seed

# 4. Levantar FastAPI
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. Verificar
# http://localhost:8000/health
# http://localhost:8000/docs (Swagger)
```

---

## ⚠️ Issues Conocidos

1. **`seed.py` importa `async_session`** que no existe en `database.py` (se llama `AsyncSessionLocal`). Necesita fix.
2. **`OperatorResponse` con `from_attributes`** espera campos flat de User+Operator, pero el modelo tiene perfil anidado.
3. **Fixture `db` en `test_operators.py`** no está definido en `conftest.py`.
4. **No hay migraciones Alembic generadas** — las tablas se crean con `Base.metadata.create_all`.
5. **Frontend sin implementar** — es el objetivo del Sprint 3.

---

## Fases del Sprint 3

| Fase | Documento | Descripción |
|---|---|---|
| 3.1 | `FASE3.1_FRONTEND_BASE.md` | Configuración base frontend + Tailwind + HTMX |
| 3.1T | `FASE3.1_TEST.md` | Pruebas automatizadas de frontend base |
| 3.2 | `FASE3.2_LANDING.md` | Landing Page móvil registro (HU05) |
| 3.2T | `FASE3.2_TEST.md` | Pruebas automatizadas de landing |
| 3.3 | `FASE3.3_ADMIN_PANEL.md` | Panel administración (HU06) + pruebas |

---

> **Al cerrar una fase:** Actualizar este documento marcando la fase como completada y agregando notas si es necesario.