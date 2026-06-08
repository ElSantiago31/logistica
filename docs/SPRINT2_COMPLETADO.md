# DOCUMENTACIÓN DE ESTADO — Sprint 2 Completado

> **Instrucción para la IA en futuras sesiones:** Al iniciar una nueva sesión o fase, por favor lee este documento primero para obtener el contexto completo del estado del proyecto hasta el cierre del Sprint 2 y saber cómo retomar el desarrollo en el Sprint 3.

## Resumen de Avance

El **Sprint 2** abordó las Historias de Usuario (HU03 y HU04) y se enfocó en el CRUD de operadores y la gestión de sus perfiles y fotos.

| Historia de Usuario | Estado | Descripción |
|-------------------|--------|-------------|
| HU03 | ✅ Completada | Registro público de operadores con subida de fotos y generación de miniaturas. |
| HU04 | ✅ Completada | CRUD de operadores (listar, detalle, editar perfil, y soft-delete) para uso de Superadmins, Coordinadores y autogestión. |

## Detalles Técnicos Implementados en Sprint 2

### 1. Esquemas (`backend/app/schemas/operators.py`)
- **`OperatorResponse`**: Retorna datos consolidados de las tablas `users` y `operators` (incluyendo `photo_path` y `photo_thumbnail_path`).
- **`OperatorListResponse`**: Lista de operadores paginada, con conteo total.
- **`OperatorUpdateRequest`**: Esquema para actualizar los datos personales, que usa el operador o el admin.
- **`OperatorAdminUpdateRequest`**: Extiende el esquema anterior, permitiendo a Superadmins cambiar estados sensibles como `is_verified`, `is_approved`, `background_check_status`, y desactivación lógica (`is_active`).

### 2. Servicios (`backend/app/services/operators.py`)
- Lógica transaccional asíncrona sobre la base de SQLAlchemy 2.0.
- Uso de `selectinload` para cargar las relaciones (`User.operator_profile`).
- **Subida de fotos**: Se valida tamaño (< 5MB) y formato. Se utiliza **Pillow** para guardar la foto original y crear una miniatura de 300x300. Se guardan con nombres generados usando UUIDs en los directorios `data/photos` y `data/photos/thumbnails`.

### 3. Rutas / Endpoints (`backend/app/routers/operators.py`)
| Endpoint | Auth | Descripción |
|----------|------|-------------|
| `GET /api/operators/` | Admin / Coordinator | Lista paginada y filtrada de operadores. |
| `GET /api/operators/{id}` | User or Admin | Detalle del operador. Validado para que un operador solo vea su propio perfil. |
| `PUT /api/operators/{id}` | User or Admin | Actualización de datos. Ignora campos administrativos si lo ejecuta un usuario regular. |
| `DELETE /api/operators/{id}` | Superadmin | Soft-delete del operador. |
| `POST /api/operators/{id}/photo` | User or Admin | Recibe un `multipart/form-data` con la foto y actualiza el perfil del operador con las rutas estáticas. |

### 4. Actualizaciones a Archivos Existentes
- **`backend/app/main.py`**:
  - Se incluyó `operators_router`.
  - Se configuró la ruta estática para acceder a las fotos vía URL: `app.mount("/static/photos", StaticFiles(directory=settings.PHOTOS_DIR), name="photos")`.

### 5. Pruebas Unitarias (`backend/tests/test_operators.py`)
- Agregados los tests de integración para listar operadores, permisos basados en token (RBAC), manipulación de datos de perfil, subida de foto dummy y borrado lógico.

---

## Próximos Pasos: Sprint 3 (Días 7-9)

El proyecto está preparado para avanzar a la parte de Frontend y Panel de Administración. Las Historias de Usuario a desarrollar son:

- **HU05**: Landing Page móvil para registro.
- **HU06**: Panel de administración (Backoffice).

### Propuesta de Fases para Sprint 3
Para continuar manteniendo el orden y evitar perder contexto:

1. **Fase 3.1: Base de Frontend y Configuración HTMX / Tailwind**
   - Configuración de la estructura de las carpetas bajo `frontend/`.
   - Cargar Tailwind via CDN o configuración local.
   - Plantilla base HTML e integración de HTMX para SPA ligera.
2. **Fase 3.2: Landing Page Móvil (HU05)**
   - Formulario de registro consumiendo `/api/auth/register` de forma interactiva con HTMX.
   - Opcional: Proceso visual para subir foto inmediatamente tras registro exitoso conectando con `/api/operators/{id}/photo`.
3. **Fase 3.3: Panel de Administración (HU06)**
   - Vistas para login de superadmin.
   - Dashboard con lista de operadores.
   - Botones para "Aprobar", "Rechazar" u opciones de edición rápida sobre la tabla.

> **Instrucción Final:** Cuando inicies la próxima sesión con el usuario, propón iniciar la **Fase 3.1** basada en esta estructura y mantén este archivo abierto o en memoria.
