# FASE 4.0 — Gestión de Eventos (HU07) + Mejora Registro Operadores

> **Sprint 4 (Días 10-12)** — Eventos, asignaciones y formulario mejorado.

---

## Estado: ✅ Completado

**Pre-requisitos:** FASE 3.1, 3.2, 3.3 completadas.

---

## Objetivo

Implementar la gestión completa de eventos (CRUD) con cuotas de personal por rol, mejoras al formulario de registro de operadores con datos laborales y tallas de uniforme, y actualización del panel admin para visualizar la nueva información.

---

## Historias de Usuario

### HU07: Creación de eventos con cuotas por rol
**Como** coordinador / superadmin,
**Quiero** crear eventos definiendo fecha, lugar y cuotas de personal por rol,
**Para** planificar la logística de cada evento.

### HU07b: Mejora de registro de operadores
**Como** operador,
**Quiero** completar datos adicionales durante el registro (dirección, WhatsApp, experiencia, tallas),
**Para** que el equipo de logística tenga toda mi información necesaria.

---

## Modelo de Datos

### Tabla `events`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | UUID PK | Identificador único |
| name | String(200) | Nombre del evento |
| code | String(20) unique | Código corto (ej: EVT-001) |
| description | Text | Descripción detallada |
| event_type | String(50) | Tipo: corporativo, social, deportivo, concierto, otro |
| status | String(20) | draft, published, in_progress, completed, cancelled |
| start_date | DateTime | Fecha/hora de inicio |
| end_date | DateTime | Fecha/hora de finalización |
| location_name | String(300) | Nombre del lugar |
| location_address | String(500) | Dirección |
| client_name | String(200) | Nombre del cliente |
| client_phone | String(20) | Teléfono del cliente |
| client_email | String(200) | Email del cliente |
| expected_attendees | Integer | Asistentes esperados |
| notes | Text | Notas internas |
| created_by | UUID FK users | Usuario que creó el evento |

### Tabla `event_staff_needs`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | UUID PK | Identificador único |
| event_id | UUID FK events | Evento asociado |
| role_id | UUID FK roles | Rol requerido |
| quantity | Integer | Cantidad de personal necesario |
| assigned_count | Integer | Cuántos ya asignados (default 0) |

### Nuevos campos en `operators`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| locality | String(150) | Localidad / Barrio |
| whatsapp | String(20) | Número WhatsApp |
| has_protocol_experience | Boolean | Experiencia en protocolo |
| event_size_experience | String(50) | Tamaño evento: 100, 500, 1000, 2000+ |
| shoe_size | String(10) | Talla de zapatos |
| shirt_size | String(10) | Talla de camisa |
| pants_size | String(10) | Talla de pantalón |
| jacket_size | String(10) | Talla de chaqueta |

---

## Archivos Creados/Modificados

### Nuevos archivos

| Archivo | Descripción |
|---------|-------------|
| `backend/app/models/events.py` | Modelos Event, EventStaffNeed, EventAssignment |
| `backend/app/schemas/events.py` | Schemas Pydantic para eventos |
| `backend/app/services/events.py` | Lógica de negocio de eventos |
| `backend/app/routers/events.py` | API endpoints de eventos |
| `backend/app/templates/admin/events.html` | Lista de eventos en admin |
| `backend/app/templates/admin/event_create.html` | Formulario crear evento |
| `backend/app/templates/admin/event_detail.html` | Detalle de evento |

### Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `backend/app/models/operators.py` | +8 campos (tallas, experiencia, ubicación) |
| `backend/app/schemas/operators.py` | Campos nuevos en Base, Response, flatten |
| `backend/app/schemas/auth.py` | `OperatorRegisterRequest` con nuevos campos |
| `backend/app/services/operators.py` | `update_operator` acepta campos nuevos |
| `backend/app/routers/auth.py` | `register_operator` guarda campos nuevos |
| `backend/app/templates/landing/index.html` | Formulario mejorado (3 secciones nuevas) |
| `backend/app/templates/admin/operator_detail.html` | Muestra tallas y experiencia |
| `backend/app/main.py` | Incluir router de eventos |

### Migraciones

| Migración | Descripción |
|-----------|-------------|
| `64953d96e4b9_add_events_tables.py` | Tablas events, event_staff_needs, event_assignments |
| `4324281308a3_add_operator_experience_sizes.py` | 8 columnas nuevas en operators |

---

## API Endpoints

### Eventos

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| GET | `/api/events/` | Listar eventos (paginado, filtrable) | Admin/Coordinador |
| POST | `/api/events/` | Crear evento | Admin/Coordinador |
| GET | `/api/events/{id}` | Detalle de evento | Admin/Coordinador |
| PUT | `/api/events/{id}` | Actualizar evento | Admin/Coordinador |
| DELETE | `/api/events/{id}` | Eliminar evento | Superadmin |
| PATCH | `/api/events/{id}/status` | Cambiar estado | Admin/Coordinador |

### Filtros disponibles en GET `/api/events/`

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| skip | int | Offset (default 0) |
| limit | int | Límite (default 100) |
| status | string | Filtrar por estado |
| event_type | string | Filtrar por tipo |
| search | string | Buscar en nombre/código |

---

## Flujo de Creación de Evento

```
Admin Panel → Eventos → "Nuevo Evento"
    │
    ├── Datos básicos: nombre, código, tipo, fechas
    ├── Ubicación: nombre lugar, dirección
    ├── Cliente: nombre, teléfono, email
    ├── Personal: añadir roles con cantidades
    └── Guardar → estado "draft"
         │
         ├── Publicar → estado "published"
         ├── Iniciar → estado "in_progress"
         └── Completar → estado "completed"
```

---

## Formulario de Registro Mejorado

### Paso 1: Datos Personales (sin cambios)
- Email, contraseña, nombre, teléfono, documento

### Paso 2: Datos Laborales (mejorado)
- EPS, ARL, ciudad, **dirección**, **localidad/barrio**
- **Número WhatsApp**
- Tipo de sangre, contacto emergencia
- **Experiencia en protocolo** (Sí/No)
- **Tamaño de evento** (Hasta 100 / 100-500 / 500-1000 / 1000-2000 / 2000+)

### Paso 3: Tallas de Uniforme (nuevo)
- **Zapatos** (número)
- **Camisa** (XS / S / M / L / XL / XXL)
- **Pantalón** (número)
- **Chaqueta** (XS / S / M / L / XL / XXL)

### Paso 4: Confirmación (sin cambios)
- Resumen y envío

---

## Panel Admin — Detalle de Operador (mejorado)

Nuevas secciones visibles:
- **Información Personal**: + WhatsApp, dirección, localidad/barrio
- **Información Laboral**: + Exp. Protocolo, Tamaño Evento
- **👕 Tallas Uniforme**: Zapatos, Camisa, Pantalón, Chaqueta (nueva sección)

---

## Cómo Verificar

### 1. Formulario mejorado
```
1. Visitar http://localhost:8000/landing
2. Llenar Paso 1 → ir a Paso 2
3. Verificar nuevos campos: dirección, localidad, WhatsApp, experiencia, tallas
4. Completar registro → verificar en BD
```

### 2. Gestión de eventos
```
1. Login en http://localhost:8000/admin/login
2. Ir a "Eventos" en el menú
3. Crear evento con datos básicos
4. Añadir necesidades de personal por rol
5. Ver detalle del evento
6. Cambiar estado del evento
```

### 3. Admin detalle operador
```
1. Ir a Operadores → seleccionar uno
2. Verificar que muestra WhatsApp, dirección, localidad
3. Verificar sección "Tallas Uniforme"
4. Verificar datos de experiencia en protocolo
```

---

## Criterios de Aceptación

- [x] CRUD completo de eventos (crear, listar, ver, editar, eliminar)
- [x] Cuotas de personal por rol en cada evento
- [x] Estados de evento: draft → published → in_progress → completed
- [x] Formulario registro con dirección, localidad, WhatsApp
- [x] Experiencia en protocolo y tamaño de evento
- [x] Tallas de uniforme (zapatos, camisa, pantalón, chaqueta)
- [x] Admin muestra todos los campos nuevos del operador
- [x] Migraciones aplicadas correctamente
- [x] Schemas y servicios actualizados

---

## Siguiente: FASE 4.1

**WhatsApp + Asignaciones** — Cola de mensajes WhatsApp (HU08), notificaciones a operadores, confirmación de asignaciones.