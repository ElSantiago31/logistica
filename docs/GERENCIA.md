# Rol "Gerencia" — Vista 360 de Eventos (Solo Lectura)

## Propósito

El rol `gerencia` permite al dueño de la empresa ver el avance de **todos los eventos** en tiempo real (asignaciones, confirmaciones, check-ins, no-shows), **sin capacidad de modificar nada**.

Es un rol de **monitoreo puro**: ningún endpoint de escritura acepta su token.

## Alta del rol (solo Superadmin)

1. Ingresar como `superadmin` → **Staff & Roles** (`/admin/superadmin`).
2. Crear usuario con rol **"Gerencia (vista 360 de eventos)"**.
3. El nuevo usuario inicia sesión en `/admin/login` y aterriza en `/gerencia`.

> Un `admin` NO puede crear usuarios gerencia: si lo intenta, el backend colapsa el rol a `checkin` (comportamiento ya cubierto por tests).

## Páginas

| Ruta | Template | Función |
|---|---|---|
| `/gerencia` | `gerencia/gerencia_events.html` | Lista de todos los eventos con barra de avance de check-in |
| `/gerencia/events/{id}` | `gerencia/gerencia_monitor.html` | Vista 360: anillos SVG (check-in %, confirmados/requeridos, pendientes, no-shows), tablas por rol / coordinador / etapa y feed de últimos check-ins. Auto-refresco cada 10 s |

## API (read-only)

| Endpoint | Descripción |
|---|---|
| `GET /api/monitoring/events` | Lista ligera de todos los eventos con `confirmed` y `checked_in` |
| `GET /api/monitoring/events/{id}/overview` | Resumen 360: `event`, `totals`, `by_role`, `by_coordinator`, `by_stage`, `recent_checkins`, `updated_at` |
| `GET /api/events` | Listado de eventos (aperturado también a monitoreo) |

### Guard central

`app/permissions.py → can_view_monitoring(user)` acepta `gerencia`, `superadmin` y `admin`. Todos los endpoints del router `monitoring.py` lo llaman (`_require_monitoring`).

## Matriz de permisos (resumen)

| Acción | gerencia | superadmin | admin | checkin |
|---|---|---|---|---|
| Ver monitoreo 360 | ✅ | ✅ | ✅ | ❌ |
| Crear/editar/eliminar eventos | ❌ (403) | ✅ | ✅ | ❌ |
| Crear usuarios staff | ❌ (403) | ✅ | ✅ (sin gerencia) | ❌ |
| Check-in operativo | ❌ | ✅ | ✅ | ✅ |

## Tests

`backend/tests/test_gerencia.py` cubre: login, prohibición de escritura en eventos, creación por superadmin, colapso de rol cuando un admin intenta crear gerencia, overview 360, lista de eventos de monitoreo y bloqueo a operadores sin asignación.

```bash
cd backend && python -m pytest tests/test_gerencia.py -q
```

## Notas de implementación

- El router `monitoring.py` **reutiliza** los helpers `_get_event_staff_needs` y `_get_coordinator_quotas` del router `sync` (una sola fuente de verdad).
- No hay migraciones de BD: `user_type` es un string y `gerencia` ya estaba en los tipos permitidos del modelo `User`.
- Las páginas `/gerencia/*` no usan el nav de admin: son páginas independientes con guard client-side + validación de token en cada fetch.