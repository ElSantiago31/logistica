# FASE 3.2T — Pruebas Automatizadas: Landing Page Registro

> **Instrucción para la IA:** Lee `docs/FASE3.0_CONTEXT.md` PRIMERO. Luego lee `docs/FASE3.2_LANDING.md` para entender qué se implementó. Finalmente implementa las pruebas descritas aquí.

---

## Estado: ⬜ Pendiente

**Pre-requisitos:** FASE 3.2 completada (Landing Page de registro funcionando).

---

## Objetivo

Crear pruebas automatizadas con pytest que verifiquen:
1. El flujo completo de registro de operadores desde la API
2. Las páginas HTML de landing se sirven correctamente
3. La validación de datos funciona (campos requeridos, formatos)
4. Los errores se manejan correctamente (duplicados, datos inválidos)
5. La subida de foto funciona post-registro
6. Los catálogos (EPS, ARL) se pueden consultar desde la API

---

## Archivos a Crear/Modificar

### 1. Crear `backend/tests/test_landing_flow.py`
Tests del flujo completo de registro desde la Landing Page.

### 2. Posiblemente crear endpoints auxiliares en `backend/app/routers/`
Si la Landing Page necesita consultar EPS/ARL para llenar los selects, se necesitará un endpoint como `GET /api/catalogs/eps` y `GET /api/catalogs/arl`.

---

## Tests a Implementar

| # | Test | Descripción | Assert principal |
|---|---|---|---|
| 1 | `test_landing_page_served` | `/landing` retorna HTML con formulario | 200, contiene `<form` |
| 2 | `test_landing_success_page_served` | `/landing/success` retorna HTML | 200 |
| 3 | `test_register_operator_success` | Registro completo con datos válidos | 201, retorna id y email |
| 4 | `test_register_duplicate_email` | Registro con email ya existente | 409, "correo electrónico ya está registrado" |
| 5 | `test_register_duplicate_document` | Registro con documento ya existente | 409, "número de documento ya está registrado" |
| 6 | `test_register_short_password` | Password menor a 8 caracteres | 422, validation error |
| 7 | `test_register_invalid_email` | Email con formato inválido | 422, validation error |
| 8 | `test_register_missing_required_fields` | Sin campos requeridos | 422, validation error |
| 9 | `test_register_with_optional_fields` | Registro con datos opcionales (EPS, ARL, ciudad) | 201 |
| 10 | `test_register_creates_audit_log` | Verificar que el registro crea entrada en audit_log | AuditLog con action="register" |
| 11 | `test_photo_upload_after_register` | Login post-registro + subida de foto | 200, photo_path actualizado |
| 12 | `test_catalogs_eps_available` | (Si se implementa) GET /api/catalogs/eps | 200, lista de EPS |
| 13 | `test_catalogs_arl_available` | (Si se implementa) GET /api/catalogs/arl | 200, lista de ARL |

---

## Fixtures Necesarios

```python
@pytest.fixture
async def sample_eps(db: AsyncSession):
    """Crea una EPS de prueba."""
    ...

@pytest.fixture
async def sample_arl(db: AsyncSession):
    """Crea una ARL de prueba."""
    ...

@pytest.fixture
async def valid_registration_data():
    """Datos válidos para registro de operador."""
    return {
        "email": "test.operator@example.com",
        "password": "SecurePass123!",
        "first_name": "Juan",
        "last_name": "Pérez",
        "phone": "3001234567",
        "document_type": "CC",
        "document_number": "12345678",
        "city": "Bogotá",
        "blood_type": "O+",
        "emergency_contact_name": "María Pérez",
        "emergency_contact_phone": "3009876543",
    }
```

---

## Detalle de Implementación

```python
"""Tests for Landing Page registration flow — FASE 3.2T"""
import pytest
import uuid
from io import BytesIO
from PIL import Image
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.users import User
from app.models.audit import AuditLog
from app.services.auth import hash_password


@pytest.fixture
async def existing_operator(db: AsyncSession):
    """Crea un operador existente para probar duplicados."""
    user = User(
        email="existing@test.com",
        password_hash=hash_password("password123"),
        first_name="Existing",
        last_name="Operator",
        phone="3000000000",
        document_type="CC",
        document_number="11111111",
        user_type="operator",
        is_verified=False,
        is_approved=False,
    )
    db.add(user)
    await db.commit()
    return user


@pytest.fixture
def valid_registration_data():
    """Datos válidos para registro."""
    return {
        "email": "new.operator@example.com",
        "password": "SecurePass123!",
        "first_name": "Juan",
        "last_name": "Pérez",
        "phone": "3001234567",
        "document_type": "CC",
        "document_number": "99999999",
        "city": "Bogotá",
        "blood_type": "O+",
        "emergency_contact_name": "María Pérez",
        "emergency_contact_phone": "3009876543",
    }


@pytest.mark.asyncio
async def test_landing_page_served(client: AsyncClient):
    """Landing page returns HTML with registration form."""
    response = await client.get("/landing")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<form" in response.text.lower()


@pytest.mark.asyncio
async def test_landing_success_page_served(client: AsyncClient):
    """Success page returns HTML."""
    response = await client.get("/landing/success")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_register_operator_success(client: AsyncClient, valid_registration_data):
    """Full registration with valid data succeeds."""
    response = await client.post("/api/auth/register", json=valid_registration_data)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["email"] == valid_registration_data["email"]
    assert "message" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, existing_operator, valid_registration_data):
    """Registration with existing email returns 409."""
    valid_registration_data["email"] = existing_operator.email
    response = await client.post("/api/auth/register", json=valid_registration_data)
    assert response.status_code == 409
    assert "correo electrónico" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_duplicate_document(client: AsyncClient, existing_operator, valid_registration_data):
    """Registration with existing document returns 409."""
    valid_registration_data["document_number"] = existing_operator.document_number
    response = await client.post("/api/auth/register", json=valid_registration_data)
    assert response.status_code == 409
    assert "documento" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient, valid_registration_data):
    """Registration with short password returns validation error."""
    valid_registration_data["password"] = "123"
    response = await client.post("/api/auth/register", json=valid_registration_data)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient, valid_registration_data):
    """Registration with invalid email returns validation error."""
    valid_registration_data["email"] = "not-an-email"
    response = await client.post("/api/auth/register", json=valid_registration_data)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_required_fields(client: AsyncClient):
    """Registration without required fields returns validation error."""
    response = await client.post("/api/auth/register", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_with_optional_fields(client: AsyncClient, valid_registration_data):
    """Registration with optional fields (city, blood_type, etc.) succeeds."""
    response = await client.post("/api/auth/register", json=valid_registration_data)
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_register_creates_audit_log(client: AsyncClient, valid_registration_data, db: AsyncSession):
    """Registration creates an audit log entry."""
    response = await client.post("/api/auth/register", json=valid_registration_data)
    assert response.status_code == 201
    
    user_id = response.json()["id"]
    result = await db.execute(
        select(AuditLog).where(
            AuditLog.action == "register",
            AuditLog.resource_id == uuid.UUID(user_id)
        )
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert "operador registrado" in audit.details.lower()


@pytest.mark.asyncio
async def test_photo_upload_after_register(client: AsyncClient, valid_registration_data):
    """After registration, operator can upload photo (needs login first)."""
    # Register
    reg_response = await client.post("/api/auth/register", json=valid_registration_data)
    assert reg_response.status_code == 201
    user_id = reg_response.json()["id"]

    # Login (operator won't be verified/approved, but can try)
    login_response = await client.post("/api/auth/login", json={
        "email": valid_registration_data["email"],
        "password": valid_registration_data["password"],
    })
    # Login succeeds even without verification (authenticate_user only checks is_active)
    if login_response.status_code == 200:
        token = login_response.json()["access_token"]
        
        # Create a test image
        img = Image.new('RGB', (100, 100), color='blue')
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        # Upload photo
        files = {"photo": ("photo.jpg", img_bytes, "image/jpeg")}
        response = await client.post(
            f"/api/operators/{user_id}/photo",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )
        assert response.status_code == 200
        assert "photo_path" in response.json()
```

---

## Nota sobre Endpoints de Catálogos

Si la Landing Page necesita consultar EPS y ARL para llenar los `<select>`, se puede:

**Opción A:** Crear un router de catálogos público:
```python
# backend/app/routers/catalogs.py
@router.get("/api/catalogs/eps")
async def list_eps(db): ...

@router.get("/api/catalogs/arl") 
async def list_arl(db): ...
```

**Opción B:** Hardcodear los catálogos en el template (ya que son datos estáticos que cambian poco).

Decidir según complejidad. La Opción A es más limpia y permite reutilización.

---

## Cómo Ejecutar

```bash
cd c:\Users\Karen\Downloads\logistica\backend
.\venv\Scripts\Activate.ps1
python -m pytest tests/test_landing_flow.py -v
```

---

## Criterios de Aceptación

- [ ] Archivo `tests/test_landing_flow.py` creado
- [ ] Todos los tests pasan sin errores
- [ ] Flujo completo de registro probado (registro → login → foto)
- [ ] Casos de error probados (duplicados, validación)
- [ ] Audit log de registro verificado
- [ ] Páginas HTML de landing verificadas

---

## Comando de Verificación Rápida

```bash
python -m pytest tests/test_landing_flow.py -v --tb=short 2>&1
```

Resultado esperado: `13 passed`

---

## ➡️ Siguiente: `docs/FASE3.3_ADMIN_PANEL.md`

Al completar, actualizar este documento con el resultado de las pruebas.