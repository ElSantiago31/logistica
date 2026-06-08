# FASE 3.1T — Pruebas Automatizadas: Frontend Base

> **Instrucción para la IA:** Lee `docs/FASE3.0_CONTEXT.md` PRIMERO. Luego lee `docs/FASE3.1_FRONTEND_BASE.md` para entender qué se implementó. Finalmente implementa las pruebas descritas aquí.

---

## Estado: ⬜ Pendiente

**Pre-requisitos:** FASE 3.1 completada (frontend base configurado y funcionando).

---

## Objetivo

Crear pruebas automatizadas con pytest que verifiquen que:
1. Los templates HTML se sirven correctamente
2. Los endpoints de páginas retornan HTML válido
3. Las APIs existentes no se rompieron
4. Los archivos estáticos están accesibles
5. El template base contiene los elementos esperados

---

## Archivos a Crear

### `backend/tests/test_frontend_base.py`

---

## Tests a Implementar

| # | Test | Descripción | Assert principal |
|---|---|---|---|
| 1 | `test_health_still_works` | `/health` sigue funcionando después de agregar frontend | status 200, JSON con "healthy" |
| 2 | `test_api_docs_still_works` | `/docs` (Swagger) sigue funcionando | status 200 |
| 3 | `test_test_ui_page` | `/test-ui` retorna HTML | status 200, content-type text/html |
| 4 | `test_test_ui_contains_tailwind` | La página incluye Tailwind CDN | body contiene "tailwindcss" |
| 5 | `test_test_ui_contains_htmx` | La página incluye HTMX | body contiene "htmx.org" |
| 6 | `test_landing_page_returns_html` | `/landing` retorna HTML (aunque sea placeholder) | status 200, content-type text/html |
| 7 | `test_admin_login_page_returns_html` | `/admin/login` retorna HTML | status 200 |
| 8 | `test_api_auth_login_still_works` | `/api/auth/login` sigue funcionando como API | status 401 (sin credenciales) o 422 (sin body) |
| 9 | `test_api_operators_requires_auth` | `/api/operators/` sigue protegido | status 401 o 403 |
| 10 | `test_template_base_elements` | Template base contiene navbar, footer, toast container | body contiene "Logística", "toast-container" |

---

## Fixtures Necesarios

Reutilizar los de `conftest.py`:

```python
@pytest.fixture
async def client():
    """Async HTTP client — ya existe en conftest.py"""
    ...
```

No se necesitan fixtures de DB para estos tests (son tests de serving de HTML).

---

## Detalle de Implementación

```python
"""Tests for frontend base configuration — FASE 3.1T"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_still_works(client: AsyncClient):
    """API health endpoint still works after frontend setup."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_api_docs_still_works(client: AsyncClient):
    """Swagger UI still accessible."""
    response = await client.get("/docs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_test_ui_page(client: AsyncClient):
    """Test UI page returns HTML."""
    response = await client.get("/test-ui")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_test_ui_contains_tailwind(client: AsyncClient):
    """Test UI page includes Tailwind CSS CDN."""
    response = await client.get("/test-ui")
    assert response.status_code == 200
    body = response.text
    assert "tailwindcss" in body


@pytest.mark.asyncio
async def test_test_ui_contains_htmx(client: AsyncClient):
    """Test UI page includes HTMX library."""
    response = await client.get("/test-ui")
    assert response.status_code == 200
    body = response.text
    assert "htmx.org" in body


@pytest.mark.asyncio
async def test_landing_page_returns_html(client: AsyncClient):
    """Landing page endpoint returns HTML."""
    response = await client.get("/landing")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_admin_login_page_returns_html(client: AsyncClient):
    """Admin login page returns HTML."""
    response = await client.get("/admin/login")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_api_auth_login_still_api(client: AsyncClient):
    """Auth login endpoint still works as API (returns JSON error on empty body)."""
    response = await client.post("/api/auth/login", json={})
    assert response.status_code == 422  # Validation error from Pydantic


@pytest.mark.asyncio
async def test_api_operators_requires_auth(client: AsyncClient):
    """Operators API still requires authentication."""
    response = await client.get("/api/operators/")
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_template_base_elements(client: AsyncClient):
    """Template base includes navigation, footer, and toast container."""
    response = await client.get("/test-ui")
    body = response.text
    assert "Logística" in body
    assert "toast-container" in body
```

---

## Cómo Ejecutar

```bash
cd c:\Users\Karen\Downloads\logistica\backend
.\venv\Scripts\Activate.ps1
python -m pytest tests/test_frontend_base.py -v
```

---

## Criterios de Aceptación

- [ ] Archivo `tests/test_frontend_base.py` creado con los 10 tests
- [ ] Todos los tests pasan sin errores
- [ ] Tests verifican que APIs existentes no se rompieron
- [ ] Tests verifican que templates HTML se sirven correctamente
- [ ] Tests verifican presencia de Tailwind y HTMX en las páginas

---

## Comando de Verificación Rápida

```bash
python -m pytest tests/test_frontend_base.py -v --tb=short 2>&1
```

Resultado esperado: `10 passed`

---

## ➡️ Siguiente: `docs/FASE3.2_LANDING.md`

Al completar, actualizar este documento con el resultado de las pruebas (cantidad de tests, pass/fail, notas).