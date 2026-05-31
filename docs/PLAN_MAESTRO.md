# PLAN MAESTRO — Sistema de Logística de Personal Eventual

## Timeline: 30 Días / 10 Sprints

```
Semana 1 (Días 1-9): REGISTRO Y ADMINISTRACIÓN
┌──────────┬──────────┬──────────┐
│  S1 D1-3 │  S2 D4-6 │  S3 D7-9 │
│ Infra+DB │ API CRUD │ Landing  │
│ Auth JWT │ Fotos    │ Backoffce│
│ 16 tablas│ Operators│ Admin    │
└──────────┴──────────┴──────────┘

Semana 2 (Días 10-18): EVENTOS, WHATSAPP Y PWA INICIO
┌──────────┬──────────┬──────────┐
│  S4 D10-12│ S5 D13-15│ S6 D16-18│
│ Eventos  │ Webhooks │ PWA Shell│
│ Cola WA  │ Confirms │ Sync Pre │
│ Invitar  │ Recuerdos│ Offline  │
└──────────┴──────────┴──────────┘

Semana 3 (Días 19-27): OPERACIÓN OFFLINE + NÓMINA
┌──────────┬──────────┬──────────┐
│  S7 D19-21│ S8 D22-24│ S9 D25-27│
│ QR Scan  │ Batch    │ Eval     │
│ Check-in │ Sync     │ Firmas   │
│ Offline  │ Online   │ Nómina   │
└──────────┴──────────┴──────────┘

Semana 4 (Días 28-30): CIERRE
┌──────────────────────┐
│    S10 D28-30        │
│    Reportes PDF/CSV  │
│    Producción        │
│    Documentación     │
└──────────────────────┘
```

## Stack Tecnológico

| Componente | Tecnología |
|------------|-----------|
| Backend | FastAPI + Python 3.11+ |
| DB | PostgreSQL 16 + asyncpg |
| ORM | SQLAlchemy 2.0 async |
| Migraciones | Alembic |
| Auth | JWT (python-jose) + bcrypt |
| Testing | pytest + pytest-asyncio + httpx |
| Frontend Admin | HTML + Tailwind CDN + HTMX + Vanilla JS |
| Frontend Landing | HTML + Tailwind CDN + Vanilla JS |
| PWA | Service Worker + Dexie.js + html5-qrcode |
| WhatsApp | Meta Business API + httpx async |
| Infra | Docker + Nginx + Let's Encrypt |

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

## Estructura de Directorios del Proyecto

```
logistica/
├── docs/                        # Documentación de handoff
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── database.py          # Async engine + session
│   │   ├── models/              # SQLAlchemy models
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── roles.py
│   │   │   ├── eps.py
│   │   │   ├── arl.py
│   │   │   ├── users.py
│   │   │   ├── operators.py
│   │   │   ├── events.py
│   │   │   ├── whatsapp.py
│   │   │   ├── sync.py
│   │   │   ├── payroll.py
│   │   │   └── audit.py
│   │   ├── schemas/             # Pydantic schemas
│   │   │   ├── __init__.py
│   │   │   └── auth.py
│   │   ├── routers/             # API endpoints
│   │   │   ├── __init__.py
│   │   │   └── auth.py
│   │   ├── services/            # Lógica de negocio
│   │   │   ├── __init__.py
│   │   │   └── auth.py
│   │   ├── dependencies/        # FastAPI dependencies
│   │   │   ├── __init__.py
│   │   │   └── auth.py
│   │   └── middleware/          # Middleware personalizado
│   │       ├── __init__.py
│   │       └── security.py
│   ├── alembic/                 # Migraciones
│   ├── alembic.ini
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_health.py
│   │   ├── test_config.py
│   │   ├── test_database.py
│   │   ├── test_models.py
│   │   ├── test_seed.py
│   │   ├── test_constraints.py
│   │   ├── test_crud_basic.py
│   │   ├── test_auth_login.py
│   │   ├── test_auth_jwt.py
│   │   ├── test_auth_roles.py
│   │   ├── test_auth_refresh.py
│   │   └── test_security.py
│   ├── scripts/
│   │   ├── seed.py
│   │   └── reminders_cron.py
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── public/
│   │   ├── landing/             # HU05 - Registro operadores
│   │   ├── admin/               # HU06 - Backoffice
│   │   ├── events/              # HU07 - Gestión eventos
│   │   └── pwa/                 # HU11-14 - Acreditación offline
│   ├── sw.js                    # Service Worker
│   ├── manifest.json
│   └── js/
│       ├── db.js                # Dexie.js wrapper
│       ├── scanner.js           # QR/PDF417 reader
│       ├── sync.js              # Queue + batch sync
│       └── signature.js         # Canvas pad de firmas
├── docker-compose.yml
├── .gitignore
└── .env.example
```

## Historias de Usuario (21 total)

### Sprint 1 (Días 1-3)
- HU01: Infraestructura + DB + Auth JWT
- HU02: Login seguro para Superadministrador

### Sprint 2 (Días 4-6)
- HU03: Registro público de operadores con foto
- HU04: CRUD de operadores para Superadmin

### Sprint 3 (Días 7-9)
- HU05: Landing Page móvil para registro
- HU06: Panel de administración

### Sprint 4 (Días 10-12)
- HU07: Creación de eventos con cuotas por rol
- HU08: Cola de mensajes WhatsApp

### Sprint 5 (Días 13-15)
- HU09: Webhook confirmaciones WhatsApp
- HU10: Recordatorios automáticos

### Sprint 6 (Días 16-18)
- HU11: PWA instalable + descarga datos offline
- HU12: Descarga de fotos para verificación offline

### Sprint 7 (Días 19-21)
- HU13: Escáner QR/PDF417 offline
- HU14: Verificación visual de identidad

### Sprint 8 (Días 22-24)
- HU15: Batch sync automático al recuperar conexión
- HU16: Dashboard de sincronización

### Sprint 9 (Días 25-27)
- HU17: Evaluación post-evento de operadores
- HU18: Firma digital para nómina
- HU19: Cálculo automático de nómina

### Sprint 10 (Días 28-30)
- HU20: Reportes PDF/CSV
- HU21: Documentación + pase a producción

## Seguridad Integrada

| Sprint | Elemento de Seguridad |
|--------|----------------------|
| S1 | JWT + RBAC + CORS + Rate Limit + HTTPS + Fail2ban + Auditoría |
| S2 | Validación MIME + Resize fotos + EXIF strip + UUID names |
| S3 | httpOnly cookies + Auto-logout + Datos parciales + URLs firmadas |
| S4 | Autorización por rol + Cola persistente + Rate limit Meta API |
| S5 | HMAC webhook + Anti-replay + Validación teléfono |
| S6 | Token efímero un solo uso + Datos mínimos offline + HMAC |
| S7 | Match por UUID + Log local scans + Anti-duplicado |
| S8 | HMAC por registro + Server-wins conflictos + Paginación |
| S9 | Hash firma SHA-256 + Hash nómina + Auditoría recálculo |
| S10 | URLs firmadas temporales + Watermark + Checklist final |