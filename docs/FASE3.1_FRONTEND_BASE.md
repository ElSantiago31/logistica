# FASE 3.1 — Configuración Base del Frontend

> **Instrucción para la IA:** Lee `docs/FASE3.0_CONTEXT.md` PRIMERO para obtener contexto completo del proyecto. Luego implementa lo descrito en este documento.

---

## Estado: ⬜ Pendiente

**Pre-requisitos:** Sprint 1 y 2 completados (backend con auth + operators CRUD funcionando).

---

## Objetivo

Configurar la infraestructura base del frontend para que FastAPI sirva archivos HTML con Tailwind CSS (CDN) y HTMX, estableciendo el template base que reutilizarán todas las páginas del sistema.

---

## Decisiones de Diseño

| Decisión | Opción elegida | Razón |
|---|---|---|
| **CSS Framework** | Tailwind CDN | Sin build step, prototipado rápido |
| **Interactividad** | HTMX | SPA ligera sin framework JS pesado |
| **Template Engine** | Jinja2 (viene con FastAPI) | Templates server-side, sencillo |
| **Serve de archivos** | FastAPI StaticFiles + JinjaTemplates | Todo desde el mismo servidor |
| **Estructura** | `frontend/public/` para HTML, `frontend/js/` para JS | Ya creada en Sprint 1 |

---

## Archivos a Crear/Modificar

### 1. Crear `backend/app/templates/base.html`
Template base Jinja2 con:
- `<head>`: meta viewport, Tailwind CDN, HTMX CDN, CSS custom mínimo
- `<nav>`: barra de navegación responsive (se oculta en landing)
- `{% block content %}`: contenido dinámico
- `{% block scripts %}`: scripts adicionales por página
- Toast container para notificaciones HTMX

### 2. Crear `backend/app/templates/`
Directorio para todos los templates Jinja2 del proyecto.

### 3. Modificar `backend/app/main.py`
- Agregar `Jinja2Templates` para servir templates
- Montar `frontend/public/` como archivos estáticos (CSS, imágenes adicionales)
- Montar `frontend/js/` como estáticos
- Agregar ruta raíz `/` que redirija a landing o admin según estado
- Agregar rutas para servir cada sección HTML

### 4. Crear página de prueba `backend/app/templates/test.html`
- Página sencilla que herede de `base.html`
- Muestra "Frontend base funcionando ✅"
- Usa clases Tailwind y un atributo HTMX de prueba

---

## Detalle de Implementación

### `backend/app/templates/base.html`

```html
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Logística{% endblock %}</title>
    
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    
    <!-- HTMX -->
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    
    <!-- Tailwind custom config -->
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        primary: { 50: '#eff6ff', 100: '#dbeafe', 500: '#3b82f6', 600: '#2563eb', 700: '#1d4ed8', 800: '#1e40af', 900: '#1e3a8a' },
                        brand: '#1e40af',
                    }
                }
            }
        }
    </script>
    
    <style>
        /* Toast notifications */
        .toast { animation: slideIn 0.3s ease-out; }
        @keyframes slideIn { from { transform: translateY(-100%); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
        /* Loading indicator for HTMX */
        .htmx-indicator { display: none; }
        .htmx-request .htmx-indicator { display: inline-block; }
        .htmx-request.htmx-indicator { display: inline-block; }
    </style>
    
    {% block head %}{% endblock %}
</head>
<body class="bg-gray-50 min-h-screen">
    
    <!-- Navigation bar -->
    <nav class="bg-primary-800 text-white shadow-lg" id="main-nav">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16">
                <div class="flex items-center">
                    <a href="/" class="text-xl font-bold">📦 Logística</a>
                </div>
                <div class="flex items-center space-x-4">
                    <a href="/admin" class="hover:text-primary-200">Admin</a>
                    <a href="/landing" class="hover:text-primary-200">Registro</a>
                </div>
            </div>
        </div>
    </nav>

    <!-- Toast container -->
    <div id="toast-container" class="fixed top-4 right-4 z-50 space-y-2"></div>

    <!-- Main content -->
    <main>
        {% block content %}{% endblock %}
    </main>

    <!-- Footer -->
    <footer class="bg-gray-800 text-gray-400 text-center py-4 mt-8">
        <p>&copy; 2024 Logística — Gestión de Personal Eventual</p>
    </footer>

    {% block scripts %}{% endblock %}
</body>
</html>
```

### Modificaciones a `backend/app/main.py`

```python
# Agregar imports
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request

# Configurar templates y estáticos
templates = Jinja2Templates(directory="../frontend/public")

# Montar estáticos del frontend
app.mount("/static/frontend", StaticFiles(directory="../frontend/public"), name="frontend_static")
app.mount("/static/js", StaticFiles(directory="../frontend/js"), name="frontend_js")

# Rutas HTML (agregar DESPUÉS de los routers API)
@app.get("/landing", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse("landing/index.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("admin/index.html", {"request": request})

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})

@app.get("/test-ui", response_class=HTMLResponse)
async def test_ui(request: Request):
    return templates.TemplateResponse("test.html", {"request": request})
```

### Estructura final de archivos:

```
frontend/
├── js/                          # JS personalizado (futuro)
└── public/
    ├── test.html                # Página de prueba
    ├── landing/
    │   └── index.html           # (placeholder para FASE3.2)
    └── admin/
        ├── index.html           # (placeholder para FASE3.3)
        └── login.html           # (placeholder para FASE3.3)
```

---

## Cómo Verificar

1. Levantar FastAPI: `uvicorn app.main:app --reload`
2. Visitar `http://localhost:8000/test-ui` → Debe mostrar página con Tailwind estilizada
3. Verificar que Tailwind cargó (colores y estilos aplicados)
4. Verificar que HTMX cargó (sin errores en consola del navegador)
5. Verificar que `/health` sigue funcionando (API no afectada)
6. Verificar que `/docs` sigue funcionando (Swagger no afectado)

---

## Criterios de Aceptación

- [ ] Template base `base.html` creado con Tailwind CDN + HTMX
- [ ] FastAPI sirve templates HTML via Jinja2Templates
- [ ] Archivos estáticos del frontend se sirven correctamente
- [ ] Página `/test-ui` funciona y muestra estilos Tailwind
- [ ] APIs existentes (`/health`, `/docs`, `/api/auth/*`, `/api/operators/*`) no se rompen
- [ ] Navegación responsive básica funciona
- [ ] Toast container para notificaciones está en el template

---

## ➡️ Siguiente: `docs/FASE3.1_TEST.md`

Una vez completada esta fase, actualizar este documento marcando los criterios como ✅ y proceder a las pruebas automatizadas.