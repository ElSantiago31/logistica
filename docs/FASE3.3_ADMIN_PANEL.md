# FASE 3.3 — Panel de Administración / Backoffice (HU06) + Pruebas

> **Instrucción para la IA:** Lee `docs/FASE3.0_CONTEXT.md` PRIMERO. Luego lee `docs/FASE3.1_FRONTEND_BASE.md` (configuración base) y `docs/FASE3.2_LANDING.md` (landing page como referencia). Finalmente implementa lo descrito aquí.

---

## Estado: ⬜ Pendiente

**Pre-requisitos:** FASE 3.1, 3.1T, 3.2 y 3.2T completadas.

---

## Objetivo

Crear el Panel de Administración (Backoffice) donde el Superadmin y Coordinadores gestionan operadores, aprueban registros y visualizan el estado del sistema. Esta es la **HU06: Panel de administración**.

---

## Historia de Usuario (HU06)

**Como** superadministrador / coordinador,
**Quiero** un panel de administración web para gestionar operadores y aprobar registros,
**Para** tener control sobre quién participa en los eventos.

---

## Funcionalidad

1. **Login de admin** — Página de login para superadmin/coordinadores
2. **Dashboard** — Resumen: operadores pendientes, aprobados, total
3. **Lista de operadores** — Tabla paginada con filtros y búsqueda
4. **Aprobar/Rechazar** — Acciones rápidas sobre operadores pendientes
5. **Detalle de operador** — Ver/editar perfil completo
6. **Cerrar sesión** — Logout con revocación de token

---

## Archivos a Crear/Modificar

### Templates HTML

| Archivo | Descripción |
|---|---|
| `frontend/public/admin/login.html` | Página de login para admins |
| `frontend/public/admin/index.html` | Dashboard principal |
| `frontend/public/admin/operators.html` | Lista de operadores |
| `frontend/public/admin/operator_detail.html` | Detalle/editar operador |
| `frontend/public/admin/partials/operator_row.html` | Fila HTMX para la tabla |
| `frontend/public/admin/partials/operator_actions.html` | Botones de acción HTMX |
| `frontend/public/admin/partials/stats_cards.html` | Tarjetas de estadísticas |
| `frontend/public/admin/partials/toast.html` | Template de toast notification |

### Backend (nuevos endpoints si se necesitan)

| Archivo | Descripción |
|---|---|
| `backend/app/routers/pages.py` | Router para servir páginas HTML del admin (opcional, puede ir en main.py) |

### Tests

| Archivo | Descripción |
|---|---|
| `backend/tests/test_admin_panel.py` | Pruebas automatizadas del panel |

---

## Detalle de Implementación

### 1. Login de Admin (`admin/login.html`)

```
┌─────────────────────────────┐
│                             │
│      📦 Logística           │
│     Panel de Admin          │
│                             │
│  [ Email            ]       │
│  [ Contraseña       ]       │
│                             │
│  [  Iniciar Sesión  ]       │
│                             │
│  ¿Eres operador? Regístrate │
│                             │
└─────────────────────────────┘
```

- No hereda navbar del template base (página limpia, centrada)
- Submit via JS fetch a `POST /api/auth/login`
- Al éxito: guarda tokens en `localStorage` y redirige a `/admin`
- Al error: muestra toast rojo

### 2. Dashboard (`admin/index.html`)

```
┌──────────────────────────────────────────┐
│ 📦 Logística   [Operadores] [Cerrar SES] │
├──────────────────────────────────────────┤
│                                          │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐    │
│  │  42  │ │  38  │ │   4  │ │  12  │    │
│  │Total │ │Aprob.│ │Pend. │ │Nuevos│    │
│  └──────┘ └──────┘ └──────┘ └──────┘    │
│                                          │
│  ── Operadores Pendientes ──             │
│  ┌────────────────────────────────────┐  │
│  │ Nombre  │ Email │ Estado │ Acción │  │
│  │─────────│───────│────────│────────│  │
│  │ Juan P. │ j@... │ Pend.  │ ✅ ❌ │  │
│  │ María L │ m@... │ Pend.  │ ✅ ❌ │  │
│  └────────────────────────────────────┘  │
│                                          │
└──────────────────────────────────────────┘
```

- Carga stats via fetch a `GET /api/operators/` con diferentes filtros
- Tarjetas de estadísticas con HTMX (auto-refresh)
- Tabla de pendientes con botones de aprobar/rechazar

### 3. Lista de Operadores (`admin/operators.html`)

- Tabla completa con paginación
- Filtros: estado (todos, aprobados, pendientes, rechazados), búsqueda por nombre/email
- Columnas: Nombre, Email, Teléfono, Ciudad, EPS, Estado, Verificado, Acciones
- Acciones por fila: Ver detalle, Editar, Aprobar/Rechazar, Desactivar
- Búsqueda con debounce via HTMX

### 4. Detalle de Operador (`admin/operator_detail.html`)

- Foto del operador (o placeholder)
- Todos los datos personales y laborales
- Formulario de edición (campos admin: is_verified, is_approved, background_check_status, notes)
- Botón de guardar cambios via HTMX PUT a `/api/operators/{id}`
- Botón de desactivar (soft delete)

---

## Flujo de Autenticación del Admin

```javascript
// Login
async function adminLogin(email, password) {
    const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });
    if (response.ok) {
        const data = await response.json();
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('refresh_token', data.refresh_token);
        localStorage.setItem('user', JSON.stringify(data.user));
        window.location.href = '/admin';
    }
}

// Obtener token para requests
function getAuthHeaders() {
    const token = localStorage.getItem('access_token');
    return { 'Authorization': `Bearer ${token}` };
}

// Verificar auth al cargar página admin
function checkAdminAuth() {
    const token = localStorage.getItem('access_token');
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    if (!token || !['superadmin', 'coordinator'].includes(user.user_type)) {
        window.location.href = '/admin/login';
    }
}

// Logout
async function adminLogout() {
    const token = localStorage.getItem('access_token');
    // Decodificar token para obtener jti (simplificado)
    await fetch('/api/auth/logout', {
        method: 'POST',
        headers: getAuthHeaders()
    });
    localStorage.clear();
    window.location.href = '/admin/login';
}
```

---

## Acciones HTMX del Panel

### Aprobar operador
```html
<button hx-put="/api/operators/{id}"
        hx-headers='{"Authorization": "Bearer " + getAccessToken()}'
        hx-vals='{"is_approved": true, "is_verified": true}'
        hx-target="#row-{id}"
        hx-swap="outerHTML"
        class="bg-green-500 text-white px-3 py-1 rounded">
    ✅ Aprobar
</button>
```

### Rechazar operador
```html
<button hx-put="/api/operators/{id}"
        hx-vals='{"is_approved": false}'
        hx-target="#row-{id}"
        class="bg-red-500 text-white px-3 py-1 rounded">
    ❌ Rechazar
</button>
```

---

## Pruebas Automatizadas (`tests/test_admin_panel.py`)

| # | Test | Descripción | Assert |
|---|---|---|---|
| 1 | `test_admin_login_page_served` | `/admin/login` retorna HTML | 200, text/html |
| 2 | `test_admin_dashboard_requires_auth` | `/admin` sin token redirige o muestra login | comportamiento definido |
| 3 | `test_admin_login_success` | Login con superadmin credentials | 200, retorna tokens |
| 4 | `test_admin_login_invalid_credentials` | Login con password incorrecto | 401 |
| 5 | `test_admin_list_operators` | GET `/api/operators/` con token admin | 200, lista paginada |
| 6 | `test_admin_approve_operator` | PUT `/api/operators/{id}` con is_approved=true | 200 |
| 7 | `test_admin_reject_operator` | PUT `/api/operators/{id}` con is_approved=false | 200 |
| 8 | `test_admin_verify_operator` | PUT `/api/operators/{id}` con is_verified=true | 200 |
| 9 | `test_admin_deactivate_operator` | DELETE `/api/operators/{id}` como superadmin | 204 |
| 10 | `test_operator_cannot_access_admin` | Login como operador, intentar acceder a operators list | 403 |
| 11 | `test_admin_change_password` | POST `/api/auth/change-password` | 200 |
| 12 | `test_admin_filter_operators_pending` | GET `/api/operators/?is_approved=false` | 200, solo pendientes |
| 13 | `test_admin_stats_dashboard` | Verificar que los contadores coinciden con datos reales | consistencia |

---

## Detalle de Tests

```python
"""Tests for Admin Panel — FASE 3.3"""
import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import User
from app.models.operators import Operator
from app.services.auth import hash_password


@pytest.fixture
async def superadmin(db: AsyncSession):
    user = User(
        email="admin@test.com",
        password_hash=hash_password("Admin123!"),
        first_name="Super",
        last_name="Admin",
        phone="3000000000",
        user_type="superadmin",
        is_verified=True,
        is_approved=True,
    )
    db.add(user)
    await db.commit()
    return user


@pytest.fixture
async def superadmin_token(client: AsyncClient, superadmin):
    response = await client.post("/api/auth/login", json={
        "email": "admin@test.com",
        "password": "Admin123!"
    })
    return response.json()["access_token"]


@pytest.fixture
async def pending_operators(db: AsyncSession):
    """Crea 3 operadores pendientes de aprobación."""
    operators = []
    for i in range(3):
        user = User(
            email=f"pending{i}@test.com",
            password_hash=hash_password("password123"),
            first_name=f"Pending{i}",
            last_name="Operator",
            phone=f"300000000{i}",
            document_type="CC",
            document_number=f"1000000{i}",
            user_type="operator",
            is_verified=False,
            is_approved=False,
        )
        db.add(user)
        await db.flush()
        op = Operator(user_id=user.id, city="Test City")
        db.add(op)
        operators.append(user)
    await db.commit()
    return operators


@pytest.mark.asyncio
async def test_admin_login_page_served(client: AsyncClient):
    response = await client.get("/admin/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_admin_login_success(client: AsyncClient, superadmin):
    response = await client.post("/api/auth/login", json={
        "email": "admin@test.com",
        "password": "Admin123!"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["user_type"] == "superadmin"


@pytest.mark.asyncio
async def test_admin_login_invalid_credentials(client: AsyncClient, superadmin):
    response = await client.post("/api/auth/login", json={
        "email": "admin@test.com",
        "password": "WrongPassword!"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_list_operators(client: AsyncClient, superadmin_token, pending_operators):
    response = await client.get(
        "/api/operators/",
        headers={"Authorization": f"Bearer {superadmin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3
    assert len(data["items"]) >= 3


@pytest.mark.asyncio
async def test_admin_approve_operator(client: AsyncClient, superadmin_token, pending_operators):
    operator = pending_operators[0]
    response = await client.put(
        f"/api/operators/{operator.id}",
        headers={"Authorization": f"Bearer {superadmin_token}"},
        json={"is_approved": True, "is_verified": True}
    )
    assert response.status_code == 200
    assert response.json()["is_approved"] is True
    assert response.json()["is_verified"] is True


@pytest.mark.asyncio
async def test_admin_reject_operator(client: AsyncClient, superadmin_token, pending_operators):
    operator = pending_operators[1]
    response = await client.put(
        f"/api/operators/{operator.id}",
        headers={"Authorization": f"Bearer {superadmin_token}"},
        json={"is_approved": False}
    )
    assert response.status_code == 200
    assert response.json()["is_approved"] is False


@pytest.mark.asyncio
async def test_admin_deactivate_operator(client: AsyncClient, superadmin_token, pending_operators):
    operator = pending_operators[2]
    response = await client.delete(
        f"/api/operators/{operator.id}",
        headers={"Authorization": f"Bearer {superadmin_token}"}
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_operator_cannot_access_admin_list(client: AsyncClient, pending_operators):
    """Operator cannot list operators (admin-only endpoint)."""
    # Login as operator
    response = await client.post("/api/auth/login", json={
        "email": "pending0@test.com",
        "password": "password123"
    })
    # Even if login succeeds, operator shouldn't access the list
    if response.status_code == 200:
        token = response.json()["access_token"]
        list_response = await client.get(
            "/api/operators/",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert list_response.status_code == 403


@pytest.mark.asyncio
async def test_admin_filter_pending(client: AsyncClient, superadmin_token, pending_operators):
    response = await client.get(
        "/api/operators/?is_approved=false",
        headers={"Authorization": f"Bearer {superadmin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert all(not op["is_approved"] for op in data["items"])


@pytest.mark.asyncio
async def test_admin_change_password(client: AsyncClient, superadmin_token):
    response = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {superadmin_token}"},
        json={
            "current_password": "Admin123!",
            "new_password": "NewAdmin456!",
            "confirm_new_password": "NewAdmin456!"
        }
    )
    assert response.status_code == 200
```

---

## Cómo Verificar

1. Visitar `http://localhost:8000/admin/login`
2. Login con `admin@logistica.com` / `Admin123!`
3. Ver dashboard con stats
4. Ver lista de operadores pendientes
5. Aprobar un operador → verificar cambio de estado
6. Ver detalle de operador → editar campos
7. Cerrar sesión → redirige a login
8. Ejecutar tests: `python -m pytest tests/test_admin_panel.py -v`

---

## Criterios de Aceptación

- [ ] Página de login admin funciona
- [ ] Dashboard muestra estadísticas correctas
- [ ] Lista de operadores paginada y filtrable
- [ ] Aprobar/Rechazar operadores funciona via HTMX
- [ ] Detalle de operador con edición de campos admin
- [ ] Soft-delete (desactivar) funciona
- [ ] Logout con revocación de token
- [ ] Protección de rutas (solo superadmin/coordinator)
- [ ] Tests automatizados pasan (13 tests)
- [ ] Responsive en móvil

---

## Comando de Verificación Rápida

```bash
python -m pytest tests/test_admin_panel.py -v --tb=short 2>&1
```

Resultado esperado: `13 passed`

---

## ✅ Al Completar el Sprint 3

Actualizar `docs/FASE3.0_CONTEXT.md` marcando todas las fases como completadas. El proyecto estará listo para el Sprint 4 (Eventos + WhatsApp).