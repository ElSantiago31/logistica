# Backend — Modelos y Base de Datos

> Documentación de todos los modelos SQLAlchemy del sistema.
> Última actualización: Junio 2026

---

## 1. Visión General

El sistema usa **SQLAlchemy 2.0** con el patrón **async** (asyncpg). Todos los modelos heredan de `BaseModel` que proporciona campos comunes.

### Diagrama de Entidades

```
users ──── operators ──── event_assignments ──── events
  │              │              │                    │
  │              │              │                    ├── event_staff_needs
  │              │              │                    │
  │              │              └── attendance_log   │
  │              │                                   │
  │              ├── eps                            ├── whatsapp_outbound_queue
  │              ├── arl                            ├── payroll ──── signatures
  │              └── evaluations                    └── sync_sessions
  │
  ├── roles
  ├── audit_log
  └── revoked_tokens
```

---

## 2. BaseModel (Clase Base)

**Archivo:** `app/models/base.py`  
**Tabla:** Abstracta (no se crea en BD)

Todos los modelos heredan de esta clase. Proporciona:

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID | Clave primaria, auto-generado con `uuid.uuid4` |
| `created_at` | DateTime(tz) | Fecha de creación, default `now()` |
| `updated_at` | DateTime(tz) | Fecha de actualización, auto-update `now()` |
| `is_active` | Boolean | Soft delete, default `True` |

---

## 3. User — Usuarios del Sistema

**Archivo:** `app/models/users.py`  
**Tabla:** `users`  
**Descripción:** *"Usuarios del sistema: Superadmin, Coordinador, Operador."*

| Campo | Tipo | Restricciones | Descripción |
|---|---|---|---|
| `email` | String(255) | unique, not null | Email del usuario |
| `password_hash` | String(255) | not null | Hash bcrypt de la contraseña |
| `first_name` | String(100) | not null | Nombres |
| `last_name` | String(100) | not null | Apellidos |
| `phone` | String(20) | nullable, index | Teléfono |
| `document_number` | String(20) | unique, nullable, index | Número de cédula |
| `document_type` | String(10) | default "CC" | Tipo de documento |
| `user_type` | String(20) | not null, index | `superadmin \| coordinator \| operator` |
| `role_id` | UUID FK → roles | nullable | Rol asignado (para operadores) |
| `is_verified` | Boolean | default False | Email verificado |
| `is_approved` | Boolean | default False | Aprobado por admin |
| `last_login` | String | nullable | Último inicio de sesión |
| `notes` | Text | nullable | Notas administrativas |

**Propiedades:**
- `full_name` → retorna `"{first_name} {last_name}"`

**Relaciones:**
- `role` → `Role` (muchos a uno)
- `operator_profile` → `Operator` (uno a uno, cascade delete)

---

## 4. Operator — Perfil de Operador

**Archivo:** `app/models/operators.py`  
**Tabla:** `operators`  
**Descripción:** *"Perfil extendido de operadores con datos laborales."*

| Campo | Tipo | Comentario | Descripción |
|---|---|---|---|
| `user_id` | UUID FK → users | unique, not null | Usuario asociado |
| `eps_id` | UUID FK → eps | nullable | EPS del operador |
| `arl_id` | UUID FK → arl | nullable | ARL del operador |
| `photo_path` | String(500) | nullable | Ruta foto original |
| `photo_thumbnail_path` | String(500) | nullable | Ruta foto miniatura |
| `birth_date` | Date | nullable | Fecha de nacimiento |
| `address` | String(300) | nullable | Dirección |
| `city` | String(100) | nullable | Ciudad |
| `blood_type` | String(5) | nullable | Tipo de sangre |
| `emergency_contact_name` | String(200) | nullable | Nombre contacto emergencia |
| `emergency_contact_phone` | String(20) | nullable | Teléfono contacto emergencia |
| `has_protocol_experience` | Boolean | "Experiencia en protocolo" | ¿Tiene experiencia en protocolo? |
| `event_size_experience` | String(50) | "Tamaño evento: 100,500,1000,2000+" | Tamaño máximo de evento |
| `locality` | String(150) | "Localidad/Barrio" | Localidad o barrio |
| `whatsapp` | String(20) | "Número WhatsApp" | Número de WhatsApp |
| `education_level` | String(50) | "primaria,secundaria,tecnico,tecnologo,universitario,postgrado" | Nivel educativo |
| `shoe_size` | String(10) | — | Talla de calzado |
| `shirt_size` | String(10) | — | Talla de camisa |
| `pants_size` | String(10) | — | Talla de pantalón |
| `jacket_size` | String(10) | — | Talla de chaqueta |
| `background_check_status` | String(20) | "pending \| approved \| rejected" | Estado verificación antecedentes |
| `background_check_date` | Date | — | Fecha de verificación |
| `rating_avg` | Float | "Promedio de evaluaciones" | Rating promedio |
| `total_events` | Integer | default 0 | Total eventos participados |
| `experience_roles` | Text | "JSON list of role IDs" | Roles con experiencia (JSON) |
| `notes` | Text | — | Notas |

**Relaciones:**
- `user` → `User` (uno a uno, inversa)
- `eps` → `EPS` (muchos a uno)
- `arl` → `ARL` (muchos a uno)
- `event_assignments` → `EventAssignment[]` (uno a muchos)

---

## 5. Event, EventStaffNeed, EventAssignment — Eventos

**Archivo:** `app/models/events.py`  
**Descripción:** *"Event models - events, staff needs, and assignments."*

### 5.1 Event

**Tabla:** `events`  
**Descripción:** *"Eventos configurados por coordinadores."*

| Campo | Tipo | Comentario | Descripción |
|---|---|---|---|
| `name` | String(300) | not null | Nombre del evento |
| `slug` | String(100) | unique, index | URL slug |
| `description` | Text | nullable | Descripción |
| `location` | String(500) | not null | Lugar del evento |
| `address` | String(500) | nullable | Dirección |
| `city` | String(100) | nullable | Ciudad |
| `start_date` | DateTime(tz) | not null, index | Fecha/hora inicio |
| `end_date` | DateTime(tz) | not null | Fecha/hora fin |
| `setup_date` | DateTime(tz) | nullable | Fecha/hora montaje |
| `status` | String(20) | default "draft", index | `draft \| published \| in_progress \| completed \| cancelled` |
| `created_by` | UUID FK → users | nullable | Usuario creador |
| `client_name` | String(300) | nullable | Nombre del cliente |
| `client_phone` | String(20) | nullable | Teléfono del cliente |
| `notes` | Text | nullable | Notas |

**Relaciones:**
- `creator` → `User`
- `staff_needs` → `EventStaffNeed[]` (cascade delete)
- `assignments` → `EventAssignment[]` (cascade delete)

### 5.2 EventStaffNeed

**Tabla:** `event_staff_needs`  
**Descripción:** *"Cuotas de personal por rol para un evento."*

| Campo | Tipo | Comentario | Descripción |
|---|---|---|---|
| `event_id` | UUID FK → events | not null, index | Evento |
| `role_id` | UUID FK → roles | not null, index | Rol requerido |
| `quantity_needed` | Integer | not null | Cantidad necesaria |
| `quantity_confirmed` | Integer | default 0 | Cantidad confirmada |
| `rate_per_shift` | Float | "Tarifa para este evento/rol" | Tarifa por turno |

### 5.3 EventAssignment

**Tabla:** `event_assignments`  
**Descripción:** *"Asignación de un operador a un evento con estado de confirmación."*

| Campo | Tipo | Comentario | Descripción |
|---|---|---|---|
| `event_id` | UUID FK → events | not null, index | Evento |
| `operator_id` | UUID FK → operators | not null, index | Operador asignado |
| `role_id` | UUID FK → roles | nullable | Rol del operador |
| `status` | String(20) | default "invited", index | `invited \| confirmed \| rejected \| standby \| no_show \| checked_in` |
| `whatsapp_message_id` | String(200) | nullable | ID del mensaje WhatsApp |
| `invited_at` | DateTime(tz) | nullable | Fecha invitación |
| `confirmed_at` | DateTime(tz) | nullable | Fecha confirmación |
| `rejected_at` | DateTime(tz) | nullable | Fecha rechazo |
| `reminder_sent` | Boolean | default False | ¿Se envió recordatorio? |
| `rate_applied` | Float | "Tarifa aplicada al momento de asignación" | Tarifa aplicada |

**Ciclo de estados de la asignación:**
```
invited → confirmed → checked_in
       → rejected
       → standby
       → no_show
```

---

## 6. SyncSession, AttendanceLog — Sincronización PWA

**Archivo:** `app/models/sync.py`  
**Descripción:** *"Sync and attendance models for PWA offline operation."*

### 6.1 SyncSession

**Tabla:** `sync_sessions`  
**Descripción:** *"Sesiones de sincronización PWA (pre-evento download / post-evento upload)."*

| Campo | Tipo | Comentario |
|---|---|---|
| `event_id` | UUID FK → events | Evento sincronizado |
| `synced_by` | UUID FK → users | Usuario que sincronizó |
| `session_type` | String(20) | `download \| upload` |
| `status` | String(20) | `pending \| in_progress \| completed \| failed` |
| `records_total` | Integer | Total registros |
| `records_synced` | Integer | Registros sincronizados |
| `sync_token` | String(100) | "Token efímero de un solo uso" |
| `started_at` | DateTime(tz) | Inicio |
| `completed_at` | DateTime(tz) | Fin |
| `error_message` | Text | Error si falló |

### 6.2 AttendanceLog

**Tabla:** `attendance_log`  
**Descripción:** *"Registro de asistencia/ingreso de operadores a eventos."*

| Campo | Tipo | Comentario |
|---|---|---|
| `event_id` | UUID FK → events | Evento |
| `operator_id` | UUID FK → operators | Operador |
| `assignment_id` | UUID FK → event_assignments | Asignación |
| `check_in_time` | DateTime(tz) | Hora de ingreso |
| `check_out_time` | DateTime(tz) | Hora de salida |
| `check_in_method` | String(20) | `qr \| pdf417 \| manual \| nfc` |
| `scanned_code` | String(200) | "Código QR/PDF417 escaneado" |
| `verified_by` | UUID FK → users | Verificador |
| `sync_session_id` | UUID FK → sync_sessions | Sesión de sync |
| `is_offline` | Boolean | ¿Se registró offline? |
| `device_id` | String(100) | ID del dispositivo |
| `location_lat` | Float | Latitud |
| `location_lon` | Float | Longitud |
| `notes` | Text | Notas |

---

## 7. Role — Roles de Operadores

**Archivo:** `app/models/roles.py`  
**Tabla:** `roles`  
**Descripción:** *"Roles de operadores: Bouncer, Acomodador, Logístico, Coordinador, etc."*

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | String(100), unique | Nombre del rol |
| `slug` | String(50), unique, index | Slug URL |
| `description` | Text | Descripción |
| `base_rate` | Float, comment: "Tarifa base por turno" | Tarifa base |

**Relaciones:** `users`, `event_staff_needs`

---

## 8. EPS y ARL — Catálogos de Seguridad Social

### EPS (`app/models/eps.py`)
**Tabla:** `eps` — *"EPS (Entidad Prestadora de Salud) para operadores."*

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | String(200), unique | Nombre |
| `code` | String(20), unique | Código |
| `nit` | String(20) | NIT |

### ARL (`app/models/arl.py`)
**Tabla:** `arl` — *"ARL (Administradora de Riesgos Laborales) para operadores."*

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | String(200), unique | Nombre |
| `code` | String(20), unique | Código |
| `nit` | String(20) | NIT |

---

## 9. WhatsApp — Cola de Mensajes

**Archivo:** `app/models/whatsapp.py`  
**Tabla:** `whatsapp_outbound_queue`  
**Descripción:** *"Cola de mensajes salientes de WhatsApp."*

| Campo | Tipo | Comentario |
|---|---|---|
| `event_id` | UUID FK → events | Evento |
| `assignment_id` | UUID FK → event_assignments | Asignación |
| `phone_number` | String(20), index | Número destino |
| `template_name` | String(100) | Nombre plantilla Zenvia |
| `template_params` | Text | "JSON con parámetros de la plantilla" |
| `message_type` | String(30) | `invitation \| reminder_5d \| reminder_1d \| custom` |
| `status` | String(20), index | `pending \| sent \| delivered \| read \| failed` |
| `meta_message_id` | String(200) | ID mensaje Zenvia |
| `attempts` | Integer, default 0 | Intentos de envío |
| `max_attempts` | Integer, default 3 | Máximo intentos |
| `error_message` | Text | Error si falló |
| `sent_at` | String | Fecha envío |

---

## 10. Payroll — Nómina, Evaluaciones y Firmas

**Archivo:** `app/models/payroll.py`

### 10.1 Evaluation
**Tabla:** `evaluations` — *"Evaluación post-evento de un operador."*

| Campo | Tipo | Comentario | Descripción |
|---|---|---|---|
| `event_id` | UUID FK → events | — | Evento evaluado |
| `operator_id` | UUID FK → operators | — | Operador evaluado |
| `evaluated_by` | UUID FK → users | — | Evaluador |
| `punctuality_score` | Integer | "1-5" | Puntualidad |
| `performance_score` | Integer | "1-5" | Desempeño |
| `appearance_score` | Integer | "1-5" | Presentación |
| `attitude_score` | Integer | "1-5" | Actitud |
| `overall_score` | Float | "Promedio ponderado" | Score general |
| `comments` | Text | — | Comentarios |
| `would_hire_again` | Boolean, default True | — | ¿Se contrataría de nuevo? |

### 10.2 Payroll
**Tabla:** `payroll` — *"Registro de nómina por operador por evento."*

| Campo | Tipo | Comentario |
|---|---|---|
| `event_id` | UUID FK → events | Evento |
| `operator_id` | UUID FK → operators | Operador |
| `assignment_id` | UUID FK → event_assignments | Asignación |
| `hours_worked` | Float, default 0 | Horas trabajadas |
| `rate_per_hour` | Float | Tarifa por hora |
| `total_amount` | Float | Total bruto |
| `deductions` | Float, default 0 | Deduciones |
| `net_amount` | Float | Total neto |
| `status` | String(20) | `calculated \| pending_signature \| signed \| approved \| paid` |
| `payment_method` | String(20) | `cash \| transfer \| nequi \| daviplata` |
| `payment_reference` | String(100) | Referencia de pago |
| `paid_at` | String | Fecha de pago |
| `notes` | Text | Notas |

**Ciclo de estados de nómina:**
```
calculated → pending_signature → signed → approved → paid
```

### 10.3 Signature
**Tabla:** `signatures` — *"Firma digital del operador validando su nómina."*

| Campo | Tipo | Comentario |
|---|---|---|
| `payroll_id` | UUID FK → payroll (unique) | Registro de nómina |
| `operator_id` | UUID FK → operators | Operador que firma |
| `signature_data` | Text | "Base64 del trazo canvas" |
| `signature_hash` | String(128) | "SHA-256 hash de verificación" |
| `signed_at` | String | Fecha/hora firma |
| `ip_address` | String(45) | IP del firmante |
| `device_info` | String(300) | Info del dispositivo |
| `is_offline` | Boolean | ¿Se firmó offline? |

---

## 11. AuditLog y RevokedToken — Seguridad

**Archivo:** `app/models/audit.py`

### 11.1 AuditLog
**Tabla:** `audit_log` — *"Registro de auditoría de todas las acciones del sistema."*

| Campo | Tipo | Descripción |
|---|---|---|
| `user_id` | UUID, index | Usuario que ejecutó la acción |
| `action` | String(100), index | Acción realizada |
| `resource_type` | String(50) | Tipo de recurso afectado |
| `resource_id` | UUID | ID del recurso |
| `details` | Text | Detalles adicionales |
| `ip_address` | String(45) | IP del usuario |
| `user_agent` | String(500) | User-Agent del navegador |

### 11.2 RevokedToken
**Tabla:** `revoked_tokens` — *"Tokens JWT revocados (logout, cambio de password)."*

| Campo | Tipo | Comentario |
|---|---|---|
| `token_jti` | String(100), unique, index | ID único del token JWT |
| `user_id` | UUID, index | Usuario dueño |
| `revoked_at` | DateTime(tz) | Fecha revocación |
| `reason` | String(50) | `logout \| password_change \| admin_revocation` |

---

## 12. Migraciones (Alembic)

Las migraciones se gestionan con Alembic en `backend/alembic/versions/`:

| Migración | Descripción |
|---|---|
| `64953d96e4b9_initial_schema.py` | Schema inicial completo |
| `4324281308a3_add_operator_experience_sizes.py` | Campos de experiencia y tallas |
| `add_education_level.py` | Campo nivel educativo |
| `add_experience_roles.py` | Campo roles con experiencia (JSON) |

**Comando para crear migración:**
```bash
cd backend && alembic revision --autogenerate -m "descripción"
```

**Comando para aplicar migraciones:**
```bash
cd backend && alembic upgrade head
```

---

## 13. Comentarios de Desarrollo

### Decisiones de diseño
- **UUID como PK**: Todos los IDs son UUID v4 (no auto-increment), para facilitar sincronización offline sin conflictos
- **`comment=` en campos**: SQLAlchemy usa el parámetro `comment` para documentar valores válidos directamente en la BD. Herramientas como pgAdmin pueden mostrar estos comentarios
- **Soft delete**: `is_active` en `BaseModel` permite desactivar registros sin eliminarlos
- **`ondelete="CASCADE"`**: Las FK usan cascade a nivel de BD para mantener integridad
- **`ondelete="SET NULL"`**: Cuando un usuario/rol se elimina, las referencias se limpian (no se borran en cascada)
- **JSON en Text**: `experience_roles` y `template_params` se almacenan como JSON en campos Text (no JSONB) por simplicidad
- **Base64 en firmas**: La firma digital se almacena como Base64 del canvas, con hash SHA-256 para verificación