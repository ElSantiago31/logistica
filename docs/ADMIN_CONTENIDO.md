# Administrador de Contenido Web (CMS)

Sistema de gestión de contenido para el sitio público de A&C Eventos, permitiendo a un **Web Admin** editar la home, servicios, noticias, galería y recibir solicitudes de contacto — todo persistido en la base de datos (sin `localStorage`).

## Arquitectura

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Home pública    │─────▶│  /api/content/*  │─────▶│  PostgreSQL     │
│  (Jinja2 SSR)   │◀─────│  (FastAPI)       │◀─────│  site_content   │
└─────────────────┘      └──────────────────┘      └─────────────────┘
                                ▲
                                │
┌─────────────────┐      ┌──────┴───────────┐
│  Panel Web Admin │─────▶│  fetch() API     │
│  /admin/contenido│      │  + Bearer token  │
└─────────────────┘      └──────────────────┘
```

## Componentes

### Backend

| Archivo | Descripción |
|---------|-------------|
| `app/models/content.py` | Modelos: `SiteSection`, `ServiceItem`, `NewsItem`, `GalleryItem`, `ContactRequest` |
| `app/schemas/content.py` | Schemas Pydantic para validación de entrada/salida |
| `app/services/content.py` | Lógica de negocio (CRUD, upload de imágenes, cleanup orphans) |
| `app/routers/content.py` | Endpoints REST bajo `/api/content/*` |
| `alembic/versions/add_site_content.py` | Migración que crea las tablas |
| `scripts/seed_site_content.py` | Datos iniciales (hero, about, servicios de ejemplo) |

### Frontend

| Archivo | Descripción |
|---------|-------------|
| `templates/landing/home.html` | Home pública SSR con Jinja2, consume `content` desde la BD |
| `templates/admin/content_manager.html` | Panel admin SPA (vanilla JS, fetch a API) |

## Endpoints API

### Públicos (sin auth)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/content/homepage` | Devuelve todo el contenido público (hero, servicios, noticias, galería) |
| `POST` | `/api/content/contact` | Formulario público de contacto |

### Admin (requiere token `superadmin`/`admin`/`web_admin`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/content/sections` | Lista secciones (hero/about/contact) |
| `PUT` | `/api/content/sections/{key}` | Crea/actualiza una sección |
| `GET` | `/api/content/services` | Lista servicios |
| `POST` | `/api/content/services` | Crea servicio |
| `PUT` | `/api/content/services/{id}` | Actualiza servicio |
| `DELETE` | `/api/content/services/{id}` | Elimina servicio |
| `GET/POST/PUT/DELETE` | `/api/content/news[/{id}]` | CRUD de noticias |
| `GET/POST/PUT/DELETE` | `/api/content/gallery[/{id}]` | CRUD de galería |
| `POST` | `/api/content/upload` | Sube imagen (cuota: 50 imágenes, 5MB max) |
| `POST` | `/api/content/cleanup` | Elimina imágenes huérfanas del disco |
| `GET` | `/api/content/contacts` | Lista solicitudes (filtro: `?status=new\|read\|archived`) |
| `PUT` | `/api/content/contacts/{id}` | Cambia estado de solicitud |

## Rol `web_admin`

Nuevo rol dedicado a la gestión de contenido, sin acceso a módulos operacionales (eventos, operadores, nómina):

- **Permisos:** Solo `/api/content/*` (excepto `contact` público) y `/admin/contenido`.
- **Login:** `/admin/login` → redirige a `/admin/contenido` si el rol es `web_admin`.
- **No puede:** Ver/editar eventos, operadores, nóminas, incidentes.

## Persistencia Docker

Las imágenes subidas se guardan en `./data/static/content/` (configurable vía `CONTENT_IMAGES_DIR`).

En `docker-compose.yml`, este directorio ya está mapeado como volumen persistente:

```yaml
volumes:
  - backend_data:/app/data
```

## Testing

```bash
cd backend
pytest tests/test_content.py -v
```

Cubre:
- Endpoints públicos (homepage, formulario de contacto)
- Gate de autenticación en endpoints admin
- CRUD de servicios, noticias, galería y secciones
- Flujo de estados en solicitudes de contacto

## Flujo de Deploy

1. La migración `add_site_content` corre automáticamente en el `entrypoint.sh`.
2. El seed `scripts/seed_site_content.py` puede ejecutarse para precargar datos.
3. Crear usuario `web_admin`:

```sql
INSERT INTO users (email, full_name, user_type, password_hash, is_active)
VALUES ('web@ayceventos.com', 'Web Admin', 'web_admin', '<hash>', true);
```

4. El panel admin está disponible en `/admin/contenido`.