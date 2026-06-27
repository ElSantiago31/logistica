import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test that the health endpoint returns 200 and correct structure."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test that the root endpoint returns the landing home page."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "").lower()


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient):
    """Test that security headers are added to all responses."""
    response = await client.get("/health")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("x-xss-protection") == "1; mode=block"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_docs_endpoint_available(client: AsyncClient):
    """Test that Swagger docs endpoint is accessible."""
    response = await client.get("/docs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_nonexistent_endpoint_returns_404(client: AsyncClient):
    """Test that nonexistent endpoints return 404."""
    response = await client.get("/api/nonexistent")
    assert response.status_code == 404