# Backend — Templates y Vistas (Jinja2)

> Documentación de todas las plantillas HTML del sistema.
> Última actualización: Junio 2026

---

## 1. Visión General

El sistema usa **Jinja2** (integrado en FastAPI) para renderizar HTML en el servidor. No hay framework SPA (React/Vue). La interactividad se logra con **HTMX** + **Vanilla JS**.

### Stack Frontend
- **CSS:** Tailwind CSS (CDN, sin build step)
- **JS Framework:** HTMX 1.9.12 (CDN) + Vanilla JS
- **Colores:** Paleta dorada/marrón personalizada (`primary-50` a `primary-900`, `brand: #cf9b62`)
- **PWA:** Service Worker + manifest.json

### Estructura de Templates

```
templates/
├── base.html                    # Layout base (nav, footer, scripts)
├── test.html                    # Página de pruebas
├── landing/                     # Páginas públicas (operadores)
│   ├── home.html                # Landing page
│   ├── index.html               # Formulario de enrolamiento
│   ├── success.html             # Registro exitoso
│   ├── operator_login.html      # Login operador
│   ├── operator_profile.html    # Perfil operador
│   └── forgot_password.html     # Recuperar contraseña
└── admin/                       # Panel de administración
    ├── _admin_nav.html          # Sidebar navegación (include)
    ├── login.html               # Login admin
    ├── index.html               # Dashboard
    ├── operators.html           # Lista operadores
    ├── operator_detail.html     # Detalle operador
    ├── events.html              # Lista eventos
    ├── event_create.html        # Crear/editar evento
    ├── event_detail.html        # Detalle evento
    ├── checkin.html             # Check-in (PWA offline)
    ├── payroll.html             # Nómina evento
    └── superadmin.html          # Panel superadmin
```

---

## 2. Base Layout (`base.html`)

### Estructura HTML

```html
<!DOCTYPE html>
<html lang="es">
<head>
  - Meta tags (charset, viewport, theme-color, apple-mobile-web-app)
  - PWA manifest link
  - Tailwind CSS CDN
  - HTMX CDN
  - Tailwind config custom (colores primary + brand)
  - CSS custom (animaciones toast, HTMX indicators)
  - {% block head %}{% endblock %}
</head>
<body class="bg-gray-50 min-h-screen">
  - Navbar (responsive, desktop + mobile)
  - Toast container (fixed top-right)
  - {% block content %}{% endblock %}
  - Footer (© AyC Eventos)
  - {% block scripts %}{% endblock %}
  - Service Worker registration
  - Navbar auth state logic
</body>
</html>
```

### Navbar Inteligente
- Lee `localStorage` (`access_token`, `user`) para determinar estado de sesión
- **No logueado:** Muestra "Trabaja con nosotros" → `/enrolamiento`
- **Operador logueado:** Muestra "Mi Perfil" → `/enrolamiento/perfil`
- **Admin logueado:** Muestra "Panel" → `/admin`
- **Ambos:** Muestra "Cerrar Sesión"
- Responsive: Desktop inline + Mobile hamburger menu

### Paleta de Colores

| Nombre | Hex | Uso |
|---|---|---|
| `primary-50` | `#fff2e4` | Texto claro sobre oscuro |
| `primary-100` | `#ffebd6` | Texto secundario |
| `primary-200` | `#f8d9b6` | Texto sobre nav |
| `primary-300` | `#e3be95` | Hover links |
| `primary-400` | `#d5aa7b` | — |
| `primary-500` / `brand` | `#cf9b62` | Botones CTA, bordes logo |
| `primary-600` | `#b48450` | Hover botones |
| `primary-700` | `#976e41` | — |
| `primary-800` | `#785631` | Gradiente nav |
| `primary-900` | `#5d4224` | Nav, footer |

### Bloques Jinja2
| Bloque | Descripción |
|---|---|
| `{% block title %}` | Título de la página |
| `{% block head %}` | CSS/JS adicional en `<head>` |
| `{% block content %}` | Contenido principal |
| `{% block footer %}` | Footer (por defecto el genérico) |
| `{% block scripts %}` | JS adicional antes de cerrar `</body>` |

---

## 3. Landing Pages (Públicas)

### Rutas HTML → Templates

| Ruta | Template | Descripción |
|---|---|---|
| `/` | `landing/home.html` | Landing page de la empresa |
| `/enrolamiento` | `landing/index.html` | Formulario de registro de operadores |
| `/enrolamiento/success` | `landing/success.html` | Confirmación de registro exitoso |
| `/enrolamiento/login` | `landing/operator_login.html` | Login para operadores |
| `/enrolamiento/perfil` | `landing/operator_profile.html` | Perfil del operador (protegido) |
| `/enrolamiento/forgot-password` | `landing/forgot_password.html` | Recuperar contraseña |

### `landing/home.html` — Landing Page
- Página pública de presentación de **A&C Logística**
- Información de la empresa, servicios, contacto
- CTA "Trabaja con nosotros" → `/enrolamiento`

### `landing/index.html` — Formulario de Enrolamiento
- Formulario completo de registro de operadores
- Campos: datos personales, EPS, ARL, tallas, experiencia, contacto emergencia
- Selects de EPS/ARL cargados desde API (`/api/catalogs/eps`, `/api/catalogs/arl`)
- Selects de roles cargados desde `/api/catalogs/roles`
- Photo upload con preview
- POST a `/api/auth/register` via JS

### `landing/success.html` — Registro Exitoso
- Mensaje de confirmación tras registro
- Link a login `/enrolamiento/login`

### `landing/operator_login.html` — Login Operador
- Login con documento + contraseña
- POST a `/api/auth/login`
- Guarda tokens en `localStorage`
- Redirige a `/enrolamiento/perfil`

### `landing/operator_profile.html` — Perfil Operador
- Requiere autenticación (verifica token en JS)
- Muestra datos del operador, foto, asignaciones
- Permite editar datos y subir foto
- consume `/api/operators/profile`

### `landing/forgot_password.html` — Recuperar Contraseña
- Flujo de 2 pasos:
  1. Ingresar documento + teléfono → POST `/api/auth/forgot-password`
  2. Ingresar nueva contraseña con token → POST `/api/auth/reset-password`

---

## 4. Admin Pages (Panel de Administración)

### Rutas HTML → Templates

| Ruta | Template | Descripción |
|---|---|---|
| `/admin/login` | `admin/login.html` | Login admin/coordinador |
| `/admin` | `admin/index.html` | Dashboard principal |
| `/admin/operators` | `admin/operators.html` | Lista de operadores |
| `/admin/operators/{id}` | `admin/operator_detail.html` | Detalle de operador |
| `/admin/events` | `admin/events.html` | Lista de eventos |
| `/admin/events/create` | `admin/event_create.html` | Crear evento |
| `/admin/events/{id}` | `admin/event_detail.html` | Detalle evento |
| `/admin/events/{id}/checkin` | `admin/checkin.html` | Check-in (PWA) |
| `/admin/events/{id}/payroll` | `admin/payroll.html` | Nómina del evento |
| `/admin/superadmin` | `admin/superadmin.html` | Panel superadmin |

### `admin/_admin_nav.html` — Sidebar Navegación
- Template parcial (include) con sidebar
- Links: Dashboard, Operadores, Eventos
- Se muestra en todas las páginas admin

### `admin/login.html` — Login Admin
- Login con documento + contraseña
- POST a `/api/auth/login`
- Verifica que `user_type` sea `superadmin` o `coordinator`
- Redirige a `/admin`

### `admin/index.html` — Dashboard
- Estadísticas generales:
  - Total operadores, eventos activos, asignaciones pendientes
- Usa `/api/operators/dashboard_stats` (del router operators)
- Tabla de eventos próximos
- Links rápidos a secciones

### `admin/operators.html` — Lista Operadores
- Tabla con búsqueda y filtros
- Columnas: foto, nombre, documento, teléfono, estado, rating
- Paginación
- Click → `/admin/operators/{id}`
- consume `/api/operators/`

### `admin/operator_detail.html` — Detalle Operador
- Foto, datos personales, EPS/ARL, tallas, experiencia
- Historial de eventos y evaluaciones
- Botón editar, desactivar
- consume `/api/operators/{id}`

### `admin/events.html` — Lista Eventos
- Cards/tabla con filtros por estado
- Indicadores de cobertura (confirmados/requeridos)
- Botón crear evento
- consume `/api/events/`

### `admin/event_create.html` — Crear Evento
- Formulario completo: nombre, fechas, ubicación, cliente
- Sección de necesidades de personal (roles + cantidades + tarifas)
- POST a `/api/events/`

### `admin/event_detail.html` — Detalle Evento
- Info del evento, estado, cliente
- Lista de necesidades de personal con cobertura
- Tabla de operadores asignados con estado
- Botones: asignar operadores, enviar invitaciones WhatsApp, publicar
- consume `/api/events/{id}`, `/api/events/{id}/assignments`

### `admin/checkin.html` — Check-in (PWA Offline)
- **Template más complejo** — funciona offline como PWA
- Escáner QR/PDF417 (carga `html5-qrcode` desde CDN)
- Búsqueda manual de operadores
- Estados: checked-in, pendiente
- Descarga datos antes del evento via `/api/sync/events/{id}/offline`
- Guarda check-ins en IndexedDB (Dexie.js)
- Sincroniza al recuperar conexión via `/api/sync/events/{id}/attendance`
- UI muestra indicador de estado (online/offline)

### `admin/payroll.html` — Nómina
- Tabla de nómina por operador
- Horas trabajadas, tarifa, total, deducciones, neto
- Cálculo automático via `/api/payroll/events/{id}/calculate`
- Firma digital (canvas para firma del operador)
- Exportar CSV
- consume `/api/payroll/events/{id}`

### `admin/superadmin.html` — Panel Superadmin
- Gestión de usuarios admin/coordinadores
- CRUD de admins via `/api/auth/admins`
- Configuración del sistema
- Solo accesible con `user_type="superadmin"`

---

## 5. JavaScript Integrado en Templates

### Auth State (base.html)
```javascript
// Lee token de localStorage
const token = localStorage.getItem('access_token');
const user = JSON.parse(localStorage.getItem('user') || '{}');
// Muestra/oculta nav items según estado
```

### Service Worker (base.html)
```javascript
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/frontend/sw.js').catch(()=>{});
}
```

### Logout (base.html)
```javascript
function navLogout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    window.location.href = '/';
}
```

---

## 6. Convenciones de Diseño

### Responsive
- **Mobile-first:** Todos los templates son responsive
- **Breakpoints:** `sm:`, `md:`, `lg:` de Tailwind
- **Hamburger menu** para móvil en navbar

### Colores por Función
| Elemento | Color | Clase Tailwind |
|---|---|---|
| Nav/Footer bg | `#5d4224` → `#785631` | gradient primary-900 → primary-800 |
| Botones CTA | `#cf9b62` | `bg-brand` o `style="background:#cf9b62"` |
| Texto sobre oscuro | `#f8d9b6` | `text-primary-200` |
| Fondo página | gray-50 | `bg-gray-50` |

### Interactividad
- **HTMX** para actualizaciones parciales sin recargar
- **Fetch API** para llamadas a la API REST
- **Toasts** para notificaciones (animación slideIn)
- **HTMX indicators** para loading states

### Manejo de Archivos Estáticos
- Fotos operadores: `/data/photos/` (servidas por Nginx en producción)
- Logo: `/static/frontend/logo.jpeg`
- PWA files: `/static/frontend/manifest.json`, `/static/frontend/sw.js`