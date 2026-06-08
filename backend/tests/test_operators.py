import pytest
import uuid
import os
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image

from app.models.users import User
from app.models.operators import Operator
from app.services.auth import hash_password
from app.config import settings

@pytest.fixture
async def sample_operator(db: AsyncSession):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="operator1@test.com",
        password_hash=hash_password("password"),
        first_name="Test",
        last_name="Operator",
        user_type="operator",
        is_verified=True,
        is_approved=True
    )
    db.add(user)
    await db.flush()

    operator = Operator(
        user_id=user_id,
        city="Test City"
    )
    db.add(operator)
    await db.commit()
    return user

@pytest.fixture
async def sample_admin(db: AsyncSession):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="admin1@test.com",
        password_hash=hash_password("password"),
        first_name="Admin",
        last_name="User",
        user_type="superadmin",
        is_verified=True,
        is_approved=True
    )
    db.add(user)
    await db.commit()
    return user

@pytest.fixture
async def operator_token(client: AsyncClient, sample_operator: User):
    response = await client.post("/api/auth/login", json={
        "email": sample_operator.email,
        "password": "password"
    })
    return response.json()["access_token"]

@pytest.fixture
async def admin_token(client: AsyncClient, sample_admin: User):
    response = await client.post("/api/auth/login", json={
        "email": sample_admin.email,
        "password": "password"
    })
    return response.json()["access_token"]

@pytest.mark.asyncio
async def test_list_operators_admin(client: AsyncClient, admin_token: str, sample_operator: User):
    response = await client.get(
        "/api/operators/",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(op["email"] == sample_operator.email for op in data["items"])

@pytest.mark.asyncio
async def test_list_operators_operator_forbidden(client: AsyncClient, operator_token: str):
    response = await client.get(
        "/api/operators/",
        headers={"Authorization": f"Bearer {operator_token}"}
    )
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_get_operator_self(client: AsyncClient, operator_token: str, sample_operator: User):
    response = await client.get(
        f"/api/operators/{sample_operator.id}",
        headers={"Authorization": f"Bearer {operator_token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == sample_operator.email
    assert response.json()["city"] == "Test City"

@pytest.mark.asyncio
async def test_update_operator_profile(client: AsyncClient, operator_token: str, sample_operator: User):
    response = await client.put(
        f"/api/operators/{sample_operator.id}",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"city": "New City", "phone": "1234567890"}
    )
    assert response.status_code == 200
    assert response.json()["city"] == "New City"
    assert response.json()["phone"] == "1234567890"

@pytest.mark.asyncio
async def test_update_operator_admin_fields_forbidden_for_operator(client: AsyncClient, operator_token: str, sample_operator: User):
    # Try to approve oneself
    response = await client.put(
        f"/api/operators/{sample_operator.id}",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"is_approved": False}
    )
    assert response.status_code == 200
    # Field should be ignored, remains True
    assert response.json()["is_approved"] is True

@pytest.mark.asyncio
async def test_update_operator_admin(client: AsyncClient, admin_token: str, sample_operator: User):
    # Admin can change the approval status
    response = await client.put(
        f"/api/operators/{sample_operator.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"is_approved": False, "background_check_status": "approved"}
    )
    assert response.status_code == 200
    assert response.json()["is_approved"] is False
    assert response.json()["background_check_status"] == "approved"

@pytest.mark.asyncio
async def test_delete_operator(client: AsyncClient, admin_token: str, sample_operator: User):
    response = await client.delete(
        f"/api/operators/{sample_operator.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 204

    # Now verify it's no longer listed
    list_response = await client.get(
        "/api/operators/",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    data = list_response.json()
    assert not any(op["id"] == str(sample_operator.id) for op in data["items"])

@pytest.mark.asyncio
async def test_upload_photo(client: AsyncClient, operator_token: str, sample_operator: User, tmp_path):
    # Create a dummy image
    image_path = tmp_path / "test.jpg"
    img = Image.new('RGB', (100, 100), color = 'red')
    img.save(image_path)
    
    with open(image_path, "rb") as f:
        files = {"photo": ("test.jpg", f, "image/jpeg")}
        response = await client.post(
            f"/api/operators/{sample_operator.id}/photo",
            headers={"Authorization": f"Bearer {operator_token}"},
            files=files
        )
        
    assert response.status_code == 200
    data = response.json()
    assert data["photo_path"].startswith("/static/photos/")
    assert data["photo_thumbnail_path"].startswith("/static/photos/thumbnails/")
    
    # Ensure physical files exist
    filename = data["photo_path"].split("/")[-1]
    assert os.path.exists(os.path.join(settings.PHOTOS_DIR, filename))
    assert os.path.exists(os.path.join(settings.PHOTOS_THUMBNAIL_DIR, filename))
