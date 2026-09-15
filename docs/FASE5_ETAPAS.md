# Etapas de Evento (FASE 5)

> Funcionalidad: **ETAPAS** en eventos — `previa`, `avanzada`, `evento`, `desmontaje`.
> Estado: **COMPLETADA** (Fases 1-4, septiembre 2026)

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
| `POST /api/events/{id}/assign` | + `stage` en request; `double_shift` en respuesta |
| Import Excel (`operador_import`) | Columna opcional `ETAPA` (default `evento`, inválida → warning) |
| `GET /api/payroll/events/{id}/planilla-coordinador` | + `stage` (filtra una etapa) y `group_by=stage` (una hoja por etapa) |

Ejemplo payload de asignación:

```json
{ "operator_ids": [42], "role_id": 3, "stage": "previa" }
```

## Planillas por etapa

Menú **Planilla** en la vista de nómina (`/admin/events/{id}/payroll`):

- **Por etapa** (`group_by=stage`): un Excel con una hoja por etapa en orden cronológico (PREVIA → AVANZADA → EVENTO → DESMONTAJE), o PDF.
- **Filtro global "Filtrar solo etapa"**: limita cualquier descarga a una etapa concreta (parámetro `stage`).
- Operador multi-etapa aparece en **todas** sus planillas con la fila marcada **DOBLE TURNO** (relleno amarillo + etiqueta).

## UI

- **`event_edit.html`**: bloque "Etapas del Evento" con 4 pestañas que filtran Personal Requerido y Cupos; contadores por pestaña.
- **`event_detail.html`**: chips de avance por etapa (`by_stage`), columna Etapa en needs/quotas/asignaciones, filtro por etapa, badge DOBLE TURNO, selector de etapa al asignar (default evento), coordinadores filtrados por etapa.
- **`checkin.html`**: al buscar operador aparecen todas sus asignaciones (una por etapa); indicador de doble turno.
- **`coordinator/dashboard.html`**: cupos y listados desglosados por etapa con chips.

## Tests

- `backend/tests/test_event_stages.py` — 10 tests (by_stage, duplicados, etapa inválida, doble turno, tarifas por etapa, cuotas por etapa, compatibilidad legacy).
- `backend/tests/test_operator_import.py` — parser Excel con columna ETAPA.
- Regresión completa: 161+ passed, 3 skipped (sin `stage` en payloads legacy).

## Despliegue

1. `alembic upgrade head` (aplica `add_stage_to_events`; no-destructiva).
2. Desplegar backend (modelos/schemas/servicios/routers).
3. Sin cambios en frontend aparte de templates (se sirven desde el backend).