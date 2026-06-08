# FASE 4.1 — WhatsApp + Asignaciones (HU08)

> **Sprint 4 (Días 10-12)** — Cola de mensajes WhatsApp y gestión de asignaciones.

---

## Estado: ✅ Completado

**Pre-requisitos:** FASE 4.0 completada.

---

## Objetivo

Implementar la cola de mensajes WhatsApp (simulada) para invitar y enviar recordatorios a operadores asignados, junto con la gestión de estados de asignación (confirmar/rechazar).

---

## Historias de Usuario

### HU08: Cola de mensajes WhatsApp
**Como** coordinador,
**Quiero** enviar invitaciones y recordatorios por WhatsApp a los operadores asignados,
**Para** confirmar su participación en los eventos.

---

## Funcionalidad

1. **Encolar invitaciones** — Mensajes a operadores con estado "invited"
2. **Encolar recordatorios** — Mensajes a operadores con estado "confirmed"
3. **Envío simulado** — Simula el envío de mensajes pendientes (para dev)
4. **Ver cola** — Consultar mensajes con filtros por evento y estado
5. **Actualizar estado** — Confirmar/rechazar asignaciones de operadores
6. **Botones en UI** — Integración directa en el detalle del evento

---

## API Endpoints

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| POST | `/api/whatsapp/events/{id}/invite` | Encolar invitaciones | Admin/Coord |
| POST | `/api/whatsapp/events/{id}/remind` | Encolar recordatorios | Admin/Coord |
| POST | `/api/whatsapp/send-pending` | Simular envío pendientes | Admin |
| GET | `/api/whatsapp/queue` | Ver cola de mensajes | Admin/Coord |
| PATCH | `/api/whatsapp/assignments/{id}/status` | Cambiar estado asignación | Admin/Coord |

---

## Archivos Creados/Modificados

### Nuevos

| Archivo | Descripción |
|---------|-------------|
| `backend/app/services/whatsapp.py` | Servicio WhatsApp: cola, envío simulado, recordatorios |
| `backend/app/routers/whatsapp.py` | Router con 5 endpoints |

### Modificados

| Archivo | Cambio |
|---------|--------|
| `backend/app/main.py` | Incluir router WhatsApp |
| `backend/app/templates/admin/event_detail.html` | +3 botones WhatsApp + funciones JS |

---

## Flujo de WhatsApp

```
Coordinador asigna operadores → estado "invited"
    │
    ├── 📱 "Invitar por WA" → encola mensajes tipo "invitation"
    │       │
    │       └── 📤 "Enviar Pendientes" → simula envío → estado "sent"
    │
    ├── Operador confirma → PATCH status → "confirmed"
    │       │
    │       └── 🔔 "Recordatorio" → encola mensajes tipo "reminder_1d"
    │
    └── Operador rechaza → PATCH status → "rejected"
```

---

## Estados de Mensaje

| Estado | Descripción |
|--------|-------------|
| pending | En cola, esperando envío |
| sent | Enviado (simulado) |
| delivered | Entregado al dispositivo |
| read | Leído por el operador |
| failed | Falló después de max_attempts |

---

## Estados de Asignación

| Estado | Descripción |
|--------|-------------|
| invited | Asignado, pendiente confirmación |
| confirmed | Operador confirmó participación |
| rejected | Operador rechazó |
| standby | En lista de espera |
| no_show | No se presentó al evento |
| checked_in | Registró ingreso |

---

## Cómo Verificar

```
1. Login en /admin/login
2. Ir a Eventos → crear o seleccionar un evento
3. Asignar operadores con "+ Asignar Operadores"
4. Click "📱 Invitar por WA" → verifica mensajes encolados
5. Click "📤 Enviar Pendientes" → simula envío
6. Click "🔔 Recordatorio" → encola recordatorios
7. API: GET /api/whatsapp/queue → ver cola completa
```

---

## Notas Importantes

- **Envío simulado**: En producción se reemplaza por Meta Business API
- **Tasa de éxito**: 100% en simulación (ajustable en `simulate_send_pending`)
- **Max intentos**: 3 por defecto (configurable en modelo)
- **Sin migración nueva**: Las tablas ya existían en el schema inicial

---

## Siguiente: FASE 4.2

**Webhook + Confirmaciones** — Recepción de respuestas WhatsApp (HU09), actualización automática de estados.