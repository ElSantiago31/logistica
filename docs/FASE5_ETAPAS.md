# Etapas de Evento (FASE 5)

> Funcionalidad: **ETAPAS** en eventos — `previa`, `avanzada`, `evento`, `desmontaje`.
> Estado: **COMPLETADA** (Fases 1-4, septiembre 2026) + **extensión check-in** (octubre 2026: la etapa se define en el check-in, no al asignar)

## Qué es

Un evento ya no es una unidad plana: el personal requerido, los cupos de coordinador y las asignaciones de operadores ahora tienen la dimensión **ETAPA**. Cada etapa puede tener necesidades y cupos distintos, y un mismo operador puede participar en varias etapas del mismo evento (**doble turno**, se paga cada etapa).

| Etapa | Valor `stage` | Descripción |
|---|---|---|
| Pre-montaje | `previa` | Preparación |
| Montaje avanzada | `avanzada` | Montaje |
| Evento | `evento` | Ejecución (default) |
| Desmontaje | `desmontaje` | Cierre |

## Modelo de datos

Columna `stage VARCHAR(20) NOT NULL DEFAULT 'evento'` en:

- `event_staff_needs` — personal requerido por `(event_id, role_id, stage)` (único).
- `event_assignments` — asignación de operador por etapa (índice en `stage`).
- `event_coordinator_quotas` — cupo por `(event_id, coordinador, stage)` (únicos parciales).

Constantes en `app/models/events.py`:

```python
EVENT_STAGES = ("previa", "avanzada", "evento", "desmontaje")
DEFAULT_STAGE = "evento"
```

Migración: `alembic/versions/add_stage_to_events.py` (backfill automático a `'evento'`, dedup defensivo de needs/cuotas duplicadas, índices únicos por etapa).

## Reglas de negocio

1. **Compatibilidad total**: cualquier payload sin `stage` equivale a `'evento'`. Los datos existentes quedan en `evento` sin cambios.
2. **Doble turno**: operador con ≥2 etapas en el evento → `double_shift=True`. Aparece en cada planilla de sus etapas con **fila marcada** (amarillo + etiqueta "DOBLE TURNO") y cobra la tarifa de cada etapa.
3. **Dedup por etapa**: `already_assigned` evalúa `(event, stage, operator)`. Mismo operador en `previa` y `evento` es válido; dos veces en la misma etapa se ignora.
4. **Cupo por etapa**: el consumo (`used`) cuenta solo asignaciones admitidas de la etapa de la cuota.
5. **Tarifa por etapa**: `rate_applied` se autollena desde el need `(event, role, stage)` con fallback a cualquier etapa del mismo rol.
6. **Recálculo**: `quantity_confirmed` agrupa por `(event_id, role_id, stage)`.

## API (cambios aditivos)

Todos los endpoints aceptan/devuelven `stage` (default `'evento'`). Resumen:

| Endpoint | Cambio |
|---|---|
| `POST /api/events` y `PUT /api/events/{id}` | needs/quotas con `stage`; unicidad `(role, stage)` / `(coordinador, stage)` |
| `GET /api/events/{id}` / list | + `stage` en cada need/quota/assignment + `by_stage` con `needed/confirmed/quota_total/quota_used` |
| `POST /api/events/{id}/assign` | + `stage` opcional en request (default `evento`); `double_shift` en respuesta |
| `POST /api/sync/events/{id}/checkin` | + `stage` opcional: etapa en la que ingresa el operador (default: la de su asignación) |
| `PATCH /api/sync/assignments/{id}/stage` | **Cambia la etapa** antes/después del check-in; si ya hay check-in anota `cambio_etapa:OLD->NEW` en el AttendanceLog |
| `GET /api/sync/events/{id}/attendance-log.csv` | CSV del log de ingresos con etapa y notas de cambio de etapa |
| Import Excel (`operador_import`) | Columna opcional `ETAPA` (default `evento`, inválida → warning) |
| `GET /api/payroll/events/{id}/planilla-coordinador` | + `stage` (filtra una etapa) y `group_by=stage` (una hoja por etapa) |

Ejemplo payload de asignación (la etapa aquí es opcional; el flujo recomendado es dejarla para el check-in):

```json
{ "operator_ids": [42], "role_id": 3 }
```

Ejemplo cambio de etapa:

```json
PATCH /api/sync/assignments/{id}/stage
{ "stage": "desmontaje" }
```

## Planillas por etapa

Menú **Planilla** en la vista de nómina (`/admin/events/{id}/payroll`):

- **Por etapa** (`group_by=stage`): un Excel con una hoja por etapa en orden cronológico (PREVIA → AVANZADA → EVENTO → DESMONTAJE), o PDF.
- **Filtro global "Filtrar solo etapa"**: limita cualquier descarga a una etapa concreta (parámetro `stage`).
- Operador multi-etapa aparece en **todas** sus planillas con la fila marcada **DOBLE TURNO** (relleno amarillo + etiqueta).

## Flujo "etapa se define en el check-in" (octubre 2026)

Decisión de producto: **la etapa NO se elige al asignar operadores**; se define (o corrige) en el **check-in del evento**:

1. Asignación (`event_detail.html` o referidos): sin etapa → nace en `evento`.
2. En `checkin.html` el filtro superior de etapa preselecciona la etapa del ingreso; al hacer check-in se envía esa `stage` (también offline: la cola sincroniza la etapa y detecta divergencias servidor-vs-local).
3. Si el operador llegó a otra etapa distinta, el staff usa **"Cambiar etapa"** → `PATCH /api/sync/assignments/{id}/stage`. El cambio queda anotado en el AttendanceLog (visible en el log de ingresos y su CSV).
4. El progreso por rol (`faltan X`) respeta la etapa activa del filtro.

## UI

- **`event_edit.html`**: bloque "Etapas del Evento" con 4 pestañas que filtran Personal Requerido y Cupos; contadores por pestaña.
- **`event_detail.html`**: chips de avance por etapa (`by_stage`), columna Etapa en needs/quotas/asignaciones, filtro por etapa, badge DOBLE TURNO. **Sin selector de etapa al asignar** (nota "la etapa se define en el check-in"); la búsqueda excluye solo asignados a `evento` y el selector de coordinador lista todos los cupos con su etapa.
- **`checkin.html`**: selector de etapa del check-in (preseleccionado por el filtro activo), cambio de etapa pre/post check-in, progreso por rol según etapa, doble turno visible, descarga del log CSV con etapas, alta rápida (quick-add) con etapa.
- **`coordinator/dashboard.html`**: cupos y listados desglosados por etapa con chips.

## Tests

- `backend/tests/test_event_stages.py` — 10 tests (by_stage, duplicados, etapa inválida, doble turno, tarifas por etapa, cuotas por etapa, compatibilidad legacy).
- `backend/tests/test_checkin_stage.py` — check-in con etapa, cambio de etapa (antes/después del check-in), anotación en AttendanceLog y CSV, validación de etapa inválida.
- `backend/tests/test_operator_import.py` — parser Excel con columna ETAPA.
- Regresión completa: 161+ passed, 3 skipped (sin `stage` en payloads legacy).

## Despliegue

1. `alembic upgrade head` (aplica `add_stage_to_events`; no-destructiva).
2. Desplegar backend (modelos/schemas/servicios/routers).
3. Sin cambios en frontend aparte de templates (se sirven desde el backend).