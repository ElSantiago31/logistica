# -*- coding: utf-8 -*-
"""Tests del rol "gerencia" (vista 360 de eventos, solo lectura).

FASE 1: alta del rol y login. FASE 2 ampliará con los endpoints de
monitoreo (/api/monitoring/...).
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import User
from app.services.auth import hash_password


async def _create_staff(db: AsyncSession, doc: str, user_type: str) -> User:
    u = User(
        id=uuid.uuid4(),
        email=None,
        password_hash=hash_password("password"),
        first_name="Staff",
        last_name=user_type.title(),
        user_type=user_type,
        document_type="CC",
        document_number=doc,
        is_verified=True,
        is_approved=True,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    return u


async def _login(client: AsyncClient, doc: str) -> str:
    resp = await client.post("/api/auth/login", json={
        "document_number": doc, "password": "password",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def gerencia_env(db: AsyncSession, client: AsyncClient):
    superadmin = await _create_staff(db, "99001", "superadmin")
    gerencia = await _create_staff(db, "99002", "gerencia")
    await db.commit()
    return {"superadmin": superadmin, "gerencia": gerencia}


@pytest.mark.asyncio
async def test_gerencia_can_login(client: AsyncClient, gerencia_env):
    """El rol gerencia inicia sesión normalmente y recibe su user_type."""
    resp = await client.post("/api/auth/login", json={
        "document_number": "99002", "password": "password",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["user_type"] == "gerencia"


@pytest.mark.asyncio
async def test_gerencia_cannot_create_admins(client: AsyncClient, gerencia_env):
    """Gerencia NO puede crear usuarios (no es superadmin ni admin)."""
    token = await _login(client, "99002")
    resp = await client.post(
        "/api/auth/admins",
        json={
            "first_name": "X", "last_name": "Y",
            "document_number": "99999", "password": "secret1",
            "user_type": "admin",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_superadmin_creates_gerencia(client: AsyncClient, gerencia_env):
    """Superadmin crea un usuario gerencia vía /api/auth/admins."""
    token = await _login(client, "99001")
    resp = await client.post(
        "/api/auth/admins",
        json={
            "first_name": "Dueno", "last_name": "Empresa",
            "document_number": "99003", "password": "secret1",
            "user_type": "gerencia",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text

    # Aparece en el listado de staff con su rol
    resp = await client.get("/api/auth/admins", headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 200
    types = [a["user_type"] for a in resp.json()]
    assert "gerencia" in types


@pytest.mark.asyncio
async def test_admin_cannot_create_gerencia(client: AsyncClient, db: AsyncSession):
    """Un admin NO puede crear gerencia (solo superadmin)."""
    await _create_staff(db, "99010", "admin")
    await db.commit()
    token = await _login(client, "99010")
    resp = await client.post(
        "/api/auth/admins",
        json={
            "first_name": "No", "last_name": "Debe",
            "document_number": "99011", "password": "secret1",
            "user_type": "gerencia",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text  # crea, pero colapsa a checkin
    # Verificar el colapso de rol en el listado
    resp = await client.get("/api/auth/admins", headers={
        "Authorization": f"Bearer {token}",
    })
    created = [a for a in resp.json() if a["document_number"] == "99011"]
    assert created and created[0]["user_type"] == "checkin"