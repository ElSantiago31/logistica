# Modulo de Referidos

Sistema de referidos "Acompana" (AC): un operador activo comparte su codigo,
los nuevos colaboradores se registran con el desde la landing publica y el
referente acumula metricas derivadas (no contadores).

## Flujo

1. **SuperAdmin genera el codigo** en `/admin/referrals` (o `POST /api/referrals/codes`).
   Formato: `AC-NOMBRE-XXXX` (ej: `AC-SANTIAGO-8F3K`). Un codigo por operador.
2. **El referido se registra** en la landing con el codigo. El codigo se valida
   ANTES de crear el usuario (fail-fast, transaccion atomica).
3. **La relacion queda grabada** en `referrals` (permanente e inmutable: un
   referido tiene UN solo referente, UNIQUE en `referred_operator_id`).
4. **Las metricas son calculo derivado** sobre `referrals` + `event_assignments`.

## Reglas de negocio

| Regla | Detalle |
|---|---|
| Un codigo por operador | `referral_codes.operator_id` UNIQUE |
| Relacion inmutable | No se puede cambiar ni borrar el referente de un referido |
| Deshabilitar codigo | NO afecta relaciones historicas, solo nuevos registros |
| Validacion al registrar | Codigo inexistente (404), deshabilitado (410), referente inactivo (410) |
| Autoreferido | Rechazado (400) |
| Referido duplicado | Rechazado (409) |

## Metricas derivadas (por referente)

- `total_referrals`: personas referidas.
- `active_referrals`: referidos con `operator.is_active = true`.
- `assigned_referrals`: referidos con >= 1 asignacion activa.
- `worked_referrals`: referidos con >= 1 asignacion `checked_in` (DISTINCT).
- `derived_quota`: **cupos derivados = worked_referrals**. Un cupo por cada
  referido que TRABAJO al menos un evento (no por asignarse). Varios eventos
  del mismo referido NO generan mas cupos.

## Endpoints API (SuperAdmin)

| Metodo | Ruta | Descripcion |
|---|---|---|
| GET | `/api/referrals/stats` | Metricas globales del modulo |
| GET | `/api/referrals/codes` | Lista de codigos con metricas del referente |
| POST | `/api/referrals/codes` | Generar codigo (`{"operator_id": "..."}`) |
| PATCH | `/api/referrals/codes/{id}` | Habilitar/deshabilitar (`{"is_active": bool}`) |
| GET | `/api/referrals/{operator_id}` | Detalle del referente (metricas + referidos) |
| GET | `/api/referrals/export` | Exportar referidos a Excel (.xlsx) |

Registro publico: `POST /api/auth/register` acepta `referral_code` opcional
(max 30 chars). Invalido -> 400 sin crear nada.

## Auditoria

`referral_audit_logs` registra: `code_created`, `code_activated`,
`code_deactivated`, `referral_registered`, con usuario, referente, referido y
detalle JSON.

## Migracion

`alembic/versions/add_referral_tables.py` crea `referral_codes`, `referrals`,
`referral_audit_logs`. Aplicar con `alembic upgrade head`.

## Tests

`tests/test_referrals.py` — 25 casos: generacion, validacion, creacion,
toggle, registro (happy/duplicado/autoreferido), metricas derivadas,
auditoria, endpoints API y registro publico fail-fast.


---

## Atribucion de cupos en eventos (F11)

Cuando un operador registrado con codigo de referido se asigna a un evento
**sin coordinador explicito**, el **referente** se estampa automaticamente
como quien lo programo/admitio. Asi el referido suma en las tarjetas de cupos
del check-in de su referente (programados y checked_in X/N) sin cambios de BD:
todo se deriva de los campos ya existentes (programmed_by, admitted_by,
programmed_by_operator_id, admitted_by_operator_id).

### Reglas

- **R1 - Prioridad explicita:** si al asignar se eligio un coordinador (en el
  panel admin o en la columna del Excel de importacion), esa eleccion GANA; el
  referido NO se atribuye al referente. La atribucion por referido aplica
  SOLO cuando no hay coordinador explicito.
- **R2 - Sobrecupo (sin cambios):** si el referente esta con cupo lleno (ej.
  10/10) y llega un check-in de un referido suyo, se devuelve 409 QUOTA_FULL
  con sugerencias y se permite force_overquota tras confirmacion - igual que
  hoy, por derivacion sobre admitted_by.
- **R3 - No retroactivo:** las asignaciones EXISTENTES no se modifican (sin
  backfill). La atribucion aplica solo a asignaciones NUEVAS creadas a partir
  de este cambio.

### Donde aplica

| Punto | Comportamiento |
|---|---|
| assign_operators() (app/services/events.py) | Asignacion manual (admin/staff): si no hay coordinador explicito y el operador tiene referente, se estampa al referente (FK + nombre en MAYUSCULAS). Es por-operador dentro del lote: un lote mixto referido/libre estampa solo al referido. |
| _create_assignment() (app/services/operator_import.py) | Import Excel: si la fila NO trae coordinador y el operador tiene referente, el INSERT queda con el referente estampado. El UPDATE de filas existentes (re-import) no cambia nada (R3). |
| Helper get_referrer_operator_of() (app/services/referrals.py) | Lookup referido->referente (un SELECT; None si no tiene). |
| Check-in (app/routers/sync.py) | Sin cambios: ya deriva de admitted_by; al hacer check-in de un referido, la tarjeta del referente pasa automaticamente de X/N a X+1/N. |

### Ejemplo

SANTIAGO tiene cupo 10 con 1/10. Su referido PEPITO es asignado al evento sin
coordinador; la asignacion queda programmed_by/admitted_by = SANTIAGO GOMEZ.
Al hacerle check-in, la tarjeta de SANTIAGO pasa a 2/10. Si el cupo estuviera
lleno, el check-in devuelve 409 QUOTA_FULL (sobrecupo con confirmacion, igual
que con cualquier coordinador).

### Tests

tests/test_referral_quota.py - 11 casos: helper (con/sin referente), R1 en
asignacion manual y Excel, R2 (estampado del referente, NULL sin referente,
lote mixto, user_id), R3 (re-import no cambia lo existente).
