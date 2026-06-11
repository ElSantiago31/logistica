# Backend — Routers, APIs y Servicios

> Documentación de todos los endpoints REST, servicios y esquemas del sistema.
> Última actualización: Junio 2026

---

## 1. Visión General

El backend expone una API REST bajo el prefijo `/api/*` y sirve templates HTML con Jinja2. Los routers se registran en `app/main.py`.

### Estructura

```
app/
├── routers/          # Endpoints (controllers)
│   ├── auth.py       # Prefijo: /api/auth
│   ├── operators.py  # Prefijo: /api/operators
│   ├── events.py     # Prefijo: /api/events
│   ├── catalogs.py   # Prefijo: /api/catalogs
│   ├── whatsapp.py   # Prefijo: /api/whatsapp
│   ├── sync.py       # Prefijo: /api/sync
│   ├── payroll.py    # Prefijo: /api/payroll
│   └── reports.py    # Prefijo: /api/reports
├── services/         # Lógica de negocio
├── schemas/          # Validación Pydantic
└── dependencies/     # Middleware/Dependencias
```

### Autenticación

Todos los endpoints protegidos usan `Depends(get_current_user)` o variantes:
- `get_current_user` — Decodifica JWT, retorna usuario (puede no estar activo)
- `get_current_active_user` — Verifica que el usuario esté activo
- `require_superadmin` — Solo superadmin

### Rate Limiting

Algunos endpoints usan `@limiter.limit("N/minute")` via slowapi:
- Login: 5 req/min
- Registro: 3 req/min

---

## 2. Auth Router (`/api/auth`)

**Archivo:** `app/routers/auth.py`

### Endpoints Públicos

| Método | Ruta | Descripción | Rate Limit |
|---|---|---|---|
| `POST` | `/api/auth/login` | Login con documento + contraseña | 5/min |
| `POST` | `/api/auth/register` | Registro público de operadores | 3/min |
| `POST` | `/api/auth/refresh` | Refrescar access token | — |
| `POST` | `/api/auth/forgot-password` | Solicitar reset (documento + teléfono) | — |
| `POST` | `/api/auth/reset-password` | Resetear contraseña con token | — |

### Endpoints Protegidos

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `POST` | `/api/auth/logout/{jti}` | User | Revocar token por JTI |
| `POST` | `/api/auth/change-password` | Active User | Cambiar contraseña |
| `GET` | `/api/auth/me` | Active User | Info del usuario actual |

### Endpoints Superadmin

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/auth/admins` | Crear admin/coordinador |
| `GET` | `/api/auth/admins` | Listar admins |
| `PUT` | `/api/auth/admins/{admin_id}` | Actualizar admin |
| `DELETE` | `/api/auth/admins/{admin_id}` | Desactivar admin (no eliminarse a sí mismo) |

### Detalle de Endpoints

#### `POST /api/auth/login`
```json
// Request
{ "document_number": "12345678", "password": "mipassword" }

// Response 200
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid", "email": "...", "first_name": "...",
    "last_name": "...", "user_type": "operator", "role_name": "Bouncer"
  }
}
```
- Registra audit log (`action: "login"`)
- Actualiza `last_login`

#### `POST /api/auth/register`
```json
// Request (OperatorRegisterRequest)
{
  "email": "...", "password": "...", "first_name": "...", "last_name": "...",
  "phone": "...", "document_type": "CC", "document_number": "...",
  "eps_id": "uuid", "arl_id": "uuid", "city": "...", "address": "...",
  "locality": "...", "blood_type": "O+", "emergency_contact_name": "...",
  "emergency_contact_phone": "...", "whatsapp": "...",
  "has_protocol_experience": true, "event_size_experience": "500",
  "education_level": "secundaria", "shoe_size": "42", "shirt_size": "M",
  "pants_size": "32", "jacket_size": "M", "experience_roles": ["uuid1", "uuid2"]
}
```
- Crea `User` + `Operator` en una transacción
- Auto-aprueba (`is_verified=True, is_approved=True`)
- `experience_roles` se serializa como JSON string
- Valida duplicados de email y documento (solo activos)
- Registra audit log (`action: "register"`)

#### `POST /api/auth/forgot-password`
- Verifica documento + teléfono (no revela si existe)
- Genera token JWT de recuperación (15 min)
- Retorna token para que el frontend muestre formulario de reset

#### `POST /api/auth/change-password`
- Requiere contraseña actual
- Valida que nueva contraseña y confirmación coincidan
- Registra audit log

---

## 3. Operators Router (`/api/operators`)

**Archivo:** `app/routers/operators.py`

### Endpoints del Operador (autenticado como operador)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/operators/me` | Dashboard del operador |
| `GET` | `/api/operators/profile` | Obtener mi perfil |
| `PUT` | `/api/operators/profile` | Actualizar mi perfil |
| `POST` | `/api/operators/photo/enrollment` | Subir foto durante enrolamiento |

### Endpoints Admin (coordinator/superadmin)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/operators/` | Listar operadores (con filtros) |
| `GET` | `/api/operators/{id}` | Detalle de operador |
| `PUT` | `/api/operators/{id}` | Actualizar perfil operador |
| `DELETE` | `/api/operators/{id}` | Desactivar operador (soft delete) |
| `POST` | `/api/operators/{id}/photo` | Subir foto de operador |

### Funciones Auxiliares
- `_save_operator_photo()` — Guarda foto con Pillow, genera thumbnail, retorna ruta

---

## 4. Events Router (`/api/events`)

**Archivo:** `app/routers/events.py`

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `POST` | `/api/events/` | User | Crear evento |
| `GET` | `/api/events/` | User | Listar eventos (con filtros) |
| `GET` | `/api/events/{id}` | User | Detalle del evento |
| `PUT` | `/api/events/{id}` | User | Actualizar evento |
| `DELETE` | `/api/events/{id}` | User | Eliminar evento |
| `POST` | `/api/events/{id}/assign` | User | Asignar operadores al evento |
| `GET` | `/api/events/{id}/availability` | User | Verificar disponibilidad de operadores |
| `GET` | `/api/events/{id}/assignments` | User | Listar asignaciones del evento |

### Ciclo de vida de evento
```
draft → published → in_progress → completed
                   → cancelled
```

---

## 5. Catalogs Router (`/api/catalogs`)

**Archivo:** `app/routers/catalogs.py`

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/catalogs/eps` | Listar EPS |
| `GET` | `/api/catalogs/arl` | Listar ARL |
| `GET` | `/api/catalogs/roles` | Listar roles de operadores |

Todos son endpoints públicos (sin autenticación).

---

## 6. WhatsApp Router (`/api/whatsapp`)

**Archivo:** `app/routers/whatsapp.py`

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `POST` | `/api/whatsapp/webhook` | No | Recibir mensajes entrantes (Zenvia webhook) |
| `POST` | `/api/whatsapp/events/{id}/invite` | User | Enviar invitaciones a operadores |
| `POST` | `/api/whatsapp/events/{id}/remind` | User | Enviar recordatorio |
| `POST` | `/api/whatsapp/pending` | User | Procesar cola de mensajes pendientes |
| `GET` | `/api/whatsapp/queue` | User | Ver estado de la cola |
| `GET` | `/api/whatsapp/config` | User | Ver configuración Zenvia |
| `PUT` | `/api/whatsapp/assignments/{id}` | User | Actualizar estado de asignación |

### Webhook
El webhook recibe mensajes de WhatsApp y procesa palabras clave:
- "CONFIRMAR" → `assignment.status = "confirmed"`
- "RECHAZAR" → `assignment.status = "rejected"`

---

## 7. Sync Router (`/api/sync`)

**Archivo:** `app/routers/sync.py`

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/api/sync/events/{id}/offline` | User | Descargar datos offline para un evento |
| `POST` | `/api/sync/events/{id}/attendance` | User | Sincronizar registros de asistencia |
| `GET` | `/api/sync/events/{id}/status` | User | Estado de sincronización |
| `GET` | `/api/sync/events/{id}/attendance` | User | Obtener registros de asistencia |
| `POST` | `/api/sync/events/{id}/checkin` | User | Check-in manual o QR |

### Flujo Offline
1. Antes del evento: `GET /sync/events/{id}/offline` → IndexedDB
2. Durante el evento: Check-in local, se marca `is_offline=true`
3. Al recuperar conexión: `POST /sync/events/{id}/attendance` con registros pendientes

---

## 8. Payroll Router (`/api/payroll`)

**Archivo:** `app/routers/payroll.py`

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `POST` | `/api/payroll/events/{id}/evaluations` | User | Crear evaluación post-evento |
| `GET` | `/api/payroll/events/{id}/evaluations` | User | Ver evaluaciones del evento |
| `POST` | `/api/payroll/events/{id}/calculate` | User | Calcular nómina del evento |
| `GET` | `/api/payroll/events/{id}` | User | Ver nómina del evento |
| `PUT` | `/api/payroll/{id}/status` | User | Actualizar estado de pago |
| `POST` | `/api/payroll/{id}/sign` | User | Firmar nómina (firma digital) |

### Cálculo de nómina
- Calcula `hours_worked × rate_per_hour = total_amount`
- Aplica deducciones
- `net_amount = total_amount - deductions`

---

## 9. Reports Router (`/api/reports`)

**Archivo:** `app/routers/reports.py`

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/api/reports/events/{id}/attendance.csv` | User | Exportar asistencia a CSV |
| `GET` | `/api/reports/events/{id}/payroll.csv` | User | Exportar nómina a CSV |
| `GET` | `/api/reports/events/{id}/evaluations.csv` | User | Exportar evaluaciones a CSV |
| `GET` | `/api/reports/operators.csv` | User | Exportar lista de operadores a CSV |

Todos generan archivos CSV con `StreamingResponse`.

---

## 10. Schemas Pydantic

**Archivos:** `app/schemas/`

### `schemas/auth.py`

| Schema | Uso | Campos principales |
|---|---|---|
| `LoginRequest` | Login | `document_number`, `password` |
| `LoginResponse` | Response login | `access_token`, `refresh_token`, `token_type`, `expires_in`, `user` |
| `UserBrief` | Info usuario | `id`, `email`, `first_name`, `last_name`, `user_type`, `role_name` |
| `RegisterRequest` | Registro base | Email, nombres, documento, password |
| `OperatorRegisterRequest` | Registro operador | Hereda + EPS, ARL, tallas, experiencia |
| `RegisterResponse` | Response registro | `id`, `email`, `message` |
| `RefreshTokenRequest` | Refresh | `refresh_token` |
| `ChangePasswordRequest` | Cambio password | `current_password`, `new_password`, `confirm_new_password` |

### `schemas/operators.py`
- Esquemas para CRUD de operadores con validación de campos

### `schemas/events.py`
- Esquemas para creación/actualización de eventos y asignaciones

---

## 11. Services (Lógica de Negocio)

### `services/auth.py`
- `hash_password(password)` → Hash con bcrypt
- `verify_password(plain, hash)` → Verificar hash
- `authenticate_user(db, document, password)` → Buscar usuario y verificar
- `create_access_token(user_id, email, user_type, role_name)` → JWT access (15 min)
- `create_refresh_token(user_id, email)` → JWT refresh (7 días)
- `decode_token(token)` → Decodificar JWT
- `revoke_token(db, jti, user_id, reason)` → Revocar token
- `is_token_revoked(db, jti)` → Verificar si está revocado

### `services/operators.py`
- Gestión de operadores, fotos, thumbnails

### `services/events.py`
- Gestión de eventos, asignaciones, transiciones de estado

### `services/whatsapp.py`
- Integración con Zenvia API
- Envío de plantillas, procesamiento de webhook
- Cola de mensajes con reintentos

---

## 12. Dependencies

### `dependencies/auth.py`
- `get_current_user` — Decodifica Bearer token, carga usuario de BD
- `get_current_active_user` — Extiende anterior, verifica `is_active=True`
- `require_superadmin` — Extiende anterior, verifica `user_type="superadmin"`

### `dependencies/rate_limit.py`
- Instancia de `Limiter` de slowapi
- Se aplica a endpoints específicos via decorador `@limiter.limit()`