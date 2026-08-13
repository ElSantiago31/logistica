# Sistema PQRSF — Peticiones, Quejas, Reclamos, Sugerencias y Felicitaciones

## Resumen

El sistema PQRSF permite a los ciudadanos enviar solicitudes desde un formulario público en la home (`/`) y al equipo administrativo gestionarlas desde el panel de contenido (`/admin/contenido`).

## Arquitectura

### Backend (FastAPI + SQLAlchemy)

```
backend/app/
├── models/pqrsf.py          # Modelos: PqrsfSubmission, PqrsfResponse
├── schemas/pqrsf.py         # Pydantic schemas (creación, tracking, gestión)
├── routers/pqrsf.py         # Endpoints REST (/api/pqrsf)
├── services/pqrsf.py        # Lógica de negocio (CRUD + email)
├── services/email_sender.py # Envío de correos (SMTP)
├── alembic/versions/
│   └── add_pqrsf_tables.py  # Migración: site_pqrsf + site_pqrsf_responses
└── templates/
    ├── landing/home.html    # Formulario público
    └── admin/content_manager.html  # Panel de gestión
```

### Flujo

1. El ciudadano completa el formulario en la home.
2. Se valida el `consent` (Habeas Data) y se genera un `tracking_code` único (`PQR-YYYY-NNNNN-XXXX`, con sufijo aleatorio anti-enumeración).
3. Se guarda en `site_pqrsf` con estado `new` y prioridad `low` (por defecto).
4. Se notifica en tiempo real al panel admin vía WebSocket (`manager.publish`).
5. El admin puede: cambiar estado, cambiar prioridad, responder por email, eliminar.

## API REST

### Endpoints Públicos (sin auth)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/pqrsf` | Crear PQRSF (rate limited 5/min por IP) |
| `GET`  | `/api/pqrsf/track/{tracking_code}` | Consultar estado por código (rate limited 30/min por IP) |

### Endpoints de Gestión (require_content_manager)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET`    | `/api/pqrsf` | Listar con filtros (?status=&type=&priority=) |
| `GET`    | `/api/pqrsf/{item_id}` | Detalle de una PQRSF |
| `PUT`    | `/api/pqrsf/{item_id}/status` | Cambiar estado |
| `PUT`    | `/api/pqrsf/{item_id}/priority` | Cambiar prioridad |
| `POST`   | `/api/pqrsf/{item_id}/respond` | Responder por email (rate limited 20/min) |
| `GET`    | `/api/pqrsf/{item_id}/responses` | Historial de respuestas |
| `DELETE` | `/api/pqrsf/{item_id}` | Eliminar |

## Modelos

### PqrsfSubmission (`site_pqrsf`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | PK |
| `tracking_code` | String(30) | Único, `PQR-YYYY-NNNNN-XXXX` |
| `request_type` | String(20) | `petition\|complaint\|claim\|suggestion\|congratulation` |
| `subject` | String(200) | Asunto |
| `full_name` | String(160) | Nombre del solicitante |
| `email` | String(160) | Email |
| `phone` | String(40)? | Teléfono opcional |
| `company` | String(160)? | Empresa opcional |
| `message` | Text | Mensaje detallado |
| `status` | String(20) | `new\|in_progress\|resolved\|closed` |
| `priority` | String(10) | `low\|medium\|high` |
| `assigned_to` | UUID? | FK → users.id |
| `resolved_at` | DateTime? | Fecha de resolución |
| `contacted_at` | DateTime? | Último email enviado |

### PqrsfResponse (`site_pqrsf_responses`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | PK |
| `pqrsf_id` | UUID | FK → site_pqrsf.id (CASCADE) |
| `responded_by` | UUID | FK → users.id |
| `subject` | String(200) | Asunto del email |
| `body` | Text | Cuerpo del email |
| `sent` | Boolean | Si se envió OK |
| `error_message` | Text? | Error SMTP si falló |

## Roles y Permisos

El endpoint de gestión requiere `require_content_manager`, que permite acceso a:
- `superadmin`
- `admin`
- `web_admin`

## Tests

```bash
cd backend
python -m pytest tests/test_pqrsf.py -v
```

Cobertura (13 tests):
- Creación de PQRSF (éxito y sin consent)
- Tracking por código (éxito y 404)
- Listado admin
- Actualización de estado y prioridad
- Eliminación (éxito y 404)
- Validaciones de schema

## WebSocket

Cuando se crea una PQRSF, se publica en el canal `content` con tipo `new_pqrsf`. El panel admin escucha esto y recarga la bandeja automáticamente.

## Email

El endpoint `/api/pqrsf/{id}/respond` envía un correo al solicitante usando `email_sender.py` (SMTP configurado). Si falla, se guarda el error en `error_message` para diagnóstico.

## Seguridad y Rate Limiting

| Endpoint | Límite | Razón |
|----------|--------|-------|
| `POST /api/pqrsf` | 5/min por IP | Prevenir spam del formulario público |
| `GET /api/pqrsf/track/{code}` | 30/min por IP | Prevenir enumeración de códigos |
| `POST /api/pqrsf/{id}/respond` | 20/min | Contener abuso si se compromete un admin |

**Anti-spoofing de IP**: el rate limiter usa `X-Real-IP` (inyectado por Nginx tras validación), no headers cliente-forgeables.

**Sufijo aleatorio en tracking_code**: el consecutivo anual incluye un sufijo de 4 caracteres aleatorios (ej. `PQR-2026-00001-A7K2`) para que un atacante no pueda adivinar códigos válidos secuencialmente.

**XSS en panel admin**: todos los datos del ciudadano se renderizan con `escapeHtml()` antes de insertarse en el DOM.

## Notas de Implementación

- El `tracking_code` usa formato `PQR-YYYY-NNNNN-XXXX` con secuencia anual + sufijo aleatorio.
- Rate limiting (ver tabla anterior) en todos los endpoints sensibles.
- Migraciones: `add_pqrsf_tables` (crea tablas) y `widen_pqrsf_track` (amplía tracking_code a String(30)).
- El frontend en `content_manager.html` incluye una pestaña PQRSF con filtros, modal de respuesta con textarea (reemplaza el alert de JS), cambio de estado/prioridad con selects, banner de estado SMTP y botones de WhatsApp/email.
