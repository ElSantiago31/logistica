# -*- coding: utf-8 -*-
"""Tests de permisos y flujo de aprobacion/rechazo de operadores.

Cubre el cambio de `require_superadmin` -> `require_superadmin_or_admin`
en GET /api/operators/pending, POST /{id}/approve y POST /{id}/reject.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_test_engine
from app.models.operators import Operator
from app.models.users import User
from app.services.auth import create_access_token, hash_password


async def _create_user(db, email, doc, user_type="admin", is_approved=True):
    u = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("password"),
        first_name="Test",
        last_name=email.split("@")[0],
        user_type=user_type,
        document_type="CC",
        document_number=doc,
        is_verified=True,
        is_approved=is_approved,
    )
    db.add(u)
    await db.flush()
    return u


async def _create_operator(db, user_id):
    o = Operator(user_id=user_id, city="Bogota")
    db.add(o)
    await db.flush()
    return o


def _token_for(user) -> str:
    """Token JWT directo (evita rate limit de /api/auth/login: 20/min)."""
    return create_access_token(
        user_id=user.id, email=user.email, user_type=user.user_type,
    )["token"]


def _fresh_session() -> AsyncSession:
    """Sesion nueva sobre el engine de test (ver estado commiteado)."""
    factory = async_sessionmaker(
        get_test_engine(), class_=AsyncSession, expire_on_commit=False,
    )
    return factory()


@pytest.fixture
async def approvals_env(db: AsyncSession, client: AsyncClient):
    """Escenario: superadmin, admin, checkin, operador aprobado y 2 pendientes."""
    superadmin = await _create_user(db, "super.ap@test.com", "91001", "superadmin")
    admin = await _create_user(db, "admin.ap@test.com", "91002", "admin")
    checkin = await _create_user(db, "checkin.ap@test.com", "91003", "checkin")
    operator_ok = await _create_user(db, "opok.ap@test.com", "91004", "operator", is_approved=True)

    pend1 = await _create_user(db, "pend1.ap@test.com", "91005", "operator", is_approved=False)
    pend2 = await _create_user(db, "pend2.ap@test.com", "91006", "operator", is_approved=False)
    await _create_operator(db, pend1.id)
    await _create_operator(db, pend2.id)
    await db.commit()

    return {
        "superadmin": superadmin,
        "admin": admin,
        "checkin": checkin,
        "pending1": pend1,
        "pending2": pend2,
        # Tokens JWT directos: 4 logins x 6 tests excedian el rate limit
        "tokens": {
            "superadmin": _token_for(superadmin),
            "admin": _token_for(admin),
            "checkin": _token_for(checkin),
            "operator": _token_for(operator_ok),
        },
    }


@pytest.mark.asyncio
async def test_admin_can_list_pending(client, approvals_env):
    """El rol admin puede listar pendientes (antes 403)."""
    resp = await client.get(
        "/api/operators/pending",
        headers={"Authorization": f"Bearer {approvals_env['tokens']['admin']}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    docs = {i["document_number"] for i in data["items"]}
    assert "91005" in docs and "91006" in docs
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_admin_can_approve_operator(client, approvals_env):
    """El rol admin aprueba: is_approved=True y sale del listado."""
    token = approvals_env["tokens"]["admin"]
    uid = str(approvals_env["pending1"].id)
    resp = await client.post(
        f"/api/operators/{uid}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "Operador aprobado exitosamente"

    # Verificar estado persistido con una sesion fresca (evita identity map)
    fresh = _fresh_session()
    try:
        result = await fresh.execute(
            select(User).where(User.id == approvals_env["pending1"].id)
        )
        user = result.scalar_one()
        assert user.is_approved is True
    finally:
        await fresh.close()

    # Ya no aparece en pendientes
    resp2 = await client.get(
        "/api/operators/pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    docs = {i["document_number"] for i in resp2.json()["items"]}
    assert "91005" not in docs


@pytest.mark.asyncio
async def test_superadmin_can_still_approve(client, approvals_env):
    """Regresion: superadmin mantiene acceso a pending/approve."""
    token = approvals_env["tokens"]["superadmin"]
    resp = await client.get(
        "/api/operators/pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    resp2 = await client.post(
        f"/api/operators/{approvals_env['pending2'].id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200, resp2.text


@pytest.mark.asyncio
async def test_operator_cannot_approve(client, approvals_env):
    """Un operador NO puede listar pendientes ni aprobar (403)."""
    token = approvals_env["tokens"]["operator"]
    resp = await client.get(
        "/api/operators/pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text

    resp2 = await client.post(
        f"/api/operators/{approvals_env['pending1'].id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 403, resp2.text


@pytest.mark.asyncio
async def test_checkin_cannot_approve(client, approvals_env):
    """El rol checkin NO puede listar pendientes ni aprobar (403)."""
    token = approvals_env["tokens"]["checkin"]
    resp = await client.get(
        "/api/operators/pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text

    resp2 = await client.post(
        f"/api/operators/{approvals_env['pending1'].id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 403, resp2.text


@pytest.mark.asyncio
async def test_reject_by_admin_deactivates_user(client, approvals_env):
    """Rechazo por admin: is_active=False, sale de pendientes y audita."""
    token = approvals_env["tokens"]["admin"]
    uid = str(approvals_env["pending2"].id)
    resp = await client.post(
        f"/api/operators/{uid}/reject",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"reason": "Documentos incompletos"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "Operador rechazado exitosamente"

    # Verificar estado persistido con una sesion fresca
    fresh = _fresh_session()
    try:
        result = await fresh.execute(
            select(User).where(User.id == approvals_env["pending2"].id)
        )
        user = result.scalar_one()
        assert user.is_active is False
        assert user.is_approved is False
    finally:
        await fresh.close()

    # Ya no aparece en pendientes (solo exige is_active=True)
    resp2 = await client.get(
        "/api/operators/pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    docs = {i["document_number"] for i in resp2.json()["items"]}
    assert "91006" not in docs