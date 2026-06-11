# Frontend — PWA y JavaScript

> Documentación del frontend JavaScript, PWA y capacidades offline.
> Última actualización: Junio 2026

---

## 1. Visión General

El frontend es una **PWA (Progressive Web App)** sin framework SPA. Usa Vanilla JS con librerías específicas cargadas desde CDN.

### Stack

| Componente | Librería | Versión | Carga |
|---|---|---|---|
| IndexedDB | Dexie.js | 3.2.7 | Dinámica (unpkg) |
| Escáner QR | html5-qrcode | 2.3.8 | Dinámica (unpkg) |
| CSS | Tailwind CSS | CDN | `<script>` en base.html |
| Interactividad | HTMX | 1.9.12 | `<script>` en base.html |

### Estructura

```
frontend/
├── js/
│   ├── db.js          # IndexedDB wrapper (Dexie) — offline data
│   ├── scanner.js     # QR/PDF417 escáner — check-in
│   ├── signature.js   # Firma digital — nómina
│   └── sync.js        # Sincronización offline/online
└── public/
    ├── manifest.json   # PWA manifest
    ├── sw.js           # Service Worker
    ├── logo.jpeg       # Logo app
    ├── admin/          # Archivos estáticos admin
    ├── events/
    ├── landing/
    └── pwa/
```

---

## 2. db.js — Base de Datos Offline (Dexie)

**Archivo:** `frontend/js/db.js`  
**Nombre BD:** `ayc_events` (versión 1)  
**Export:** `window.OfflineDB`

### Tablas IndexedDB

| Tabla | Clave | Índices | Descripción |
|---|---|---|---|
| `events` | `id` | `name, status, start_date, location` | Eventos descargados para offline |
| `operators` | `id` | `event_id, full_name, document_number, role_name, status, *search_terms` | Operadores asignados por evento |
| `attendance` | `++local_id` (auto-increment) | `event_id, operator_id, check_in_time, sync_status` | Registros de asistencia offline |
| `sync_meta` | `key` | `last_sync, etag` | Metadata de sincronización |

### Funciones Principales

| Función | Descripción |
|---|---|
| `initDB()` | Inicializa BD, carga Dexie dinámicamente si no existe |
| `cacheEventData(eventId, eventData)` | Descarga y almacena evento + asignaciones para uso offline |
| `searchOperators(eventId, query)` | Búsqueda local por nombre o documento |
| `logAttendance(eventId, operatorId, photoBlob)` | Registra check-in offline (`sync_status: "pending"`) |
| `getPendingAttendance()` | Obtiene registros pendientes de sincronizar |
| `markAttendanceSynced(localId)` | Marca registro como sincronizado |
| `getCachedEvents()` | Lista eventos almacenados localmente |
| `getEventOperators(eventId)` | Lista operadores de un evento |
| `getLastSync(key)` | Última fecha de sincronización |

### Carga Dinámica de Dexie

```javascript
// Si Dexie no está cargado, se inyecta dinámicamente
if (typeof Dexie === 'undefined') {
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/dexie@3.2.7/dist/dexie.js';
    document.head.appendChild(script);
}
```

### Flujo de Datos Offline

```
1. cacheEventData() → Almacena evento + operadores en IndexedDB
2. searchOperators() → Búsqueda local sin red
3. logAttendance() → Guarda check-in con sync_status: "pending"
4. syncPendingRecords() → POST /api/sync/attendance con registros pendientes
5. markAttendanceSynced() → Marca como "synced" tras confirmación del server
```

---

## 3. scanner.js — Escáner QR/PDF417

**Archivo:** `frontend/js/scanner.js`  
**Librería:** html5-qrcode 2.3.8  
**Export:** `window.Scanner`

### Funciones

| Función | Descripción |
|---|---|
| `initScanner(containerId, onResult, onError)` | Inicia cámara con escáner QR + PDF417 |
| `stopScanner()` | Detiene escáner y limpia |
| `parseScanResult(text)` | Parsea resultado: UUID → assignment_id, dígitos → document_number |
| `manualSearch(eventId, query)` | Busca operadores: primero offline, luego online |

### Configuración del Escáner

```javascript
{
    fps: 10,                        // 10 frames por segundo
    qrbox: { width: 250, height: 250 },  // Área de escaneo
    formatsToSupport: [
        Html5QrcodeSupportedFormats.QR_CODE,
        Html5QrcodeSupportedFormats.PDF_417
    ]
}
```

### Parseo de Resultados

```javascript
// UUID → assignment_id (para buscar en BD)
"550e8400-e29b-41d4-a716-446655440000" → { type: 'assignment_id', value: '...' }

// Números → document_number (cédula)
"1234567890" → { type: 'document_number', value: '1234567890' }

// Otro → unknown
"texto libre" → { type: 'unknown', value: 'texto libre' }
```

### Funcionalidades
- **Vibración**: Al escanear exitosamente, vibra 100ms (`navigator.vibrate(100)`)
- **Cámara trasera**: Usa `facingMode: "environment"` por defecto
- **Búsqueda fallback**: Primero busca en IndexedDB, luego en API si hay conexión

---

## 4. signature.js — Firma Digital

**Archivo:** `frontend/js/signature.js`  
**Export:** `window.SignaturePad` (clase)

### Clase SignaturePad

```javascript
new SignaturePad(canvasId, options?)
// options: { lineWidth: 2, strokeColor: '#1a1a1a', bgColor: '#ffffff' }
```

### Métodos

| Método | Retorna | Descripción |
|---|---|---|
| `clear()` | — | Limpia el canvas |
| `toDataURL()` | string (Base64 PNG) | Firma como data URL |
| `toBlob()` | Promise\<Blob\> | Firma como Blob PNG |
| `getHash()` | Promise\<string\> | SHA-256 hash de la firma (hex string) |
| `isValid()` | boolean | `true` si se dibujó algo |

### Eventos Soportados
- **Mouse**: mousedown, mousemove, mouseup, mouseleave
- **Touch**: touchstart, touchmove, touchend (con `preventDefault`)

### Características
- **Responsive**: Se redimensiona al contenedor padre
- **Alto fijo**: 200px
- **SHA-256**: Usa `crypto.subtle.digest` para generar hash de integridad
- El hash se envía al backend como `signature_hash` para verificación

### Flujo de Firma

```
1. Operador dibuja firma en canvas
2. signaturePad.toDataURL() → Base64 PNG → "signature_data"
3. signaturePad.getHash() → SHA-256 → "signature_hash"
4. POST /api/payroll/{id}/sign con ambos datos
5. Backend almacena firma + hash para verificación futura
```

---

## 5. sync.js — Sincronización Offline/Online

**Archivo:** `frontend/js/sync.js`  
**Export:** `window.SyncManager`  
**Depende de:** `window.OfflineDB`

### Constantes

| Constante | Valor | Descripción |
|---|---|---|
| `SYNC_BATCH_SIZE` | 20 | Registros por lote |
| `SYNC_RETRY_MS` | 30000 | Intervalo de retry (30 seg) |

### Funciones Principales

| Función | Descripción |
|---|---|
| `syncPendingRecords()` | Sincroniza registros pendientes en lotes de 20 |
| `startAutoSync()` | Inicia escucha de evento `online` + intervalo periódico |
| `stopAutoSync()` | Detiene intervalo de sincronización |
| `downloadEventOffline(eventId)` | Descarga datos del evento para uso offline |
| `getSyncStatus()` | Estado actual: pendientes, cacheados, online, syncing |

### Auto-Sync

```javascript
// Se activa al recuperar conexión
window.addEventListener('online', () => {
    setTimeout(syncPendingRecords, 2000); // Espera 2 seg
});

// Sync periódico cada 30 seg mientras hay conexión
setInterval(() => {
    if (navigator.onLine) syncPendingRecords();
}, 30000);
```

### Eventos Personalizados

| Evento | Detalle | Cuándo |
|---|---|---|
| `sync-complete` | `{ synced, failed, total }` | Al terminar sincronización |
| `event-cached` | `{ eventId }` | Al descargar evento offline |

### Flujo de Sincronización

```
Online:
  1. downloadEventOffline(eventId) → GET /api/sync/events/{id}/offline-data
  2. cacheEventData() → IndexedDB (events, operators)

Offline:
  3. logAttendance() → IndexedDB (attendance, sync_status: "pending")

Al recuperar conexión:
  4. syncPendingRecords() → POST /api/sync/attendance (lotes de 20)
  5. markAttendanceSynced() → IndexedDB (sync_status: "synced")
  6. dispatchEvent('sync-complete') → UI actualiza contadores
```

---

## 6. manifest.json — PWA Manifest

**Archivo:** `frontend/public/manifest.json`

```json
{
  "name": "AyC Eventos - Gestión de Personal",
  "short_name": "AyC Eventos",
  "description": "Gestión de personal eventual para eventos",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#5d4224",
  "theme_color": "#cf9b62",
  "orientation": "portrait-primary",
  "icons": [
    { "src": "/static/frontend/logo.jpeg", "sizes": "192x192", "type": "image/jpeg" },
    { "src": "/static/frontend/logo.jpeg", "sizes": "512x512", "type": "image/jpeg" }
  ],
  "categories": ["business", "productivity"],
  "lang": "es-CO"
}
```

| Campo | Valor | Nota |
|---|---|---|
| `display` | `standalone` | Se ve como app nativa, sin barra de URL |
| `orientation` | `portrait-primary` | Pantalla vertical obligatoria |
| `theme_color` | `#cf9b62` | Color barra de estado (brand) |
| `background_color` | `#5d4224` | Color splash screen |

---

## 7. sw.js — Service Worker

**Archivo:** `frontend/public/sw.js`  
**Cache:** `ayc-v1`

### Estrategia: Network First, Cache Fallback

```
Request GET → Intenta red → Si ok, cachea y responde
                            → Si falla, busca en cache
```

### Assets Pre-cacheados (Install)

```javascript
const STATIC_ASSETS = [
    '/',
    '/enrolamiento/login',
    '/static/frontend/logo.jpeg',
    '/manifest.json',
];
```

### Reglas de Skip

| Patrón | Razón |
|---|---|
| `method !== 'GET'` | POST/PUT/DELETE no se cachean |
| `/api/` | Llamadas API no se cachean |
| `/webhook/` | Webhooks no se cachean |

### Ciclo de Vida

```
Install → cache.addAll(STATIC_ASSETS) → skipWaiting()
Activate → borrar caches viejos → clients.claim()
Fetch → network first, cache fallback (solo GET, no API)
```

---

## 8. Integración en Templates

### Carga de Scripts

Los scripts JS no se cargan como `<script src>` estáticos. Se referencian desde los templates según necesidad:

| Template | JS Necesario | CDN adicional |
|---|---|---|
| `checkin.html` | db.js, scanner.js, sync.js | html5-qrcode, Dexie |
| `payroll.html` | signature.js | — |
| `operator_profile.html` | — | — |
| `base.html` | — | Tailwind, HTMX |

### Almacenamiento en localStorage

| Key | Contenido | Uso |
|---|---|---|
| `access_token` | JWT access token | Autenticación API |
| `refresh_token` | JWT refresh token | Renovar sesión |
| `user` | JSON `{id, email, user_type, role_name}` | Estado UI navbar |

### Nota de Implementación
- El check-in (checkin.html) usa una instancia inline de Dexie para evitar conflictos con `db.js`
- Los scripts CDN se cargan dinámicamente solo cuando se necesitan (lazy load)
- El Service Worker se registra en `base.html` para todas las páginas