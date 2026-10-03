# -*- coding: utf-8 -*-
"""Tests del directorio de operadores (pestañas Activos/Inactivos).

Cubre el fix del estado combinado en ``GET /api/operators/``:
- Vetados (``Operator.is_banned=True`` con ``User.is_active=True``) aparecen
  en la pestaña Inactivos (``is_active=false``) y NO en Activos, por lo que
  tampoco salen en los selectores de operadores para eventos.
- Fantasmas de Incorporación Rápida (``event_only``, ``is_active=False``,
  ``email=None``) no contaminan la pestaña Inactivos.
- La serialización tolera usuarios sin email (``OperatorResponse.email``
  pasó a opcional; antes → error 500).
- Bloqueados clásicos (``is_active=False``) siguen apareciendo en Inactivos.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operators import Operator
from app.models.users import User
from app.services.auth import hash_password


async def _mk_user(db, doc, user_type="operator", email=None,
                   is_active=True, is_approved=True):
    u = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("secreto123"),
        first_name="Usr",
        last_name=doc,
        user_type=user_type,
        document_type="CC",
        document_number=doc,
        is_verified=True,
        is_approved=is_approved,
        is_active=is_active,
    )
    db.add(u)
    await db.flush()
    return u


async def _login(client, doc):
    resp = await client.post("/api/auth/login", json={
        "document_number": doc, "password": "secreto123",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def dir_env(db: AsyncSession, client: AsyncClient):
    admin = await _mk_user(db, "80001", "admin")

    # Operador activo normal
    u_active = await _mk_user(db, "80002")
    db.add(Operator(user_id=u_active.id, is_banned=False))

    # Operador VETADO: user activo pero is_banned=True (POST /api/bans)
    u_banned = await _mk_user(db, "80003")
    db.add(Operator(user_id=u_banned.id, is_banned=True))

    # Operador BLOQUEADO clásico: is_active=False (bloqueo/rechazo/eliminación)
    u_blocked = await _mk_user(db, "80004", is_active=False)
    db.add(Operator(user_id=u_blocked.id, is_banned=False))

    # FANTASMA de quick-add: is_active=False, event_only, sin email
    u_ghost = await _mk_user(db, "80005", email=None, is_active=False,
                             is_approved=False)
    db.add(Operator(user_id=u_ghost.id, is_banned=False, event_only=True))

    await db.commit()

    return {
        "ids": {
            "active": str(u_active.id),
            "banned": str(u_banned.id),
            "blocked": str(u_blocked.id),
            "ghost": str(u_ghost.id),
        },
        "admin_token": await _login(client, "80001"),
    }


def _hdrs(env):
    return {"Authorization": f"Bearer {env['admin_token']}"}


async def _list_ids(client, env, is_active):
    r = await client.get(
        f"/api/operators/?is_active={str(is_active).lower()}&limit=1000",
        headers=_hdrs(env),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    return {it["id"] for it in data["items"]}, data


class TestDirectoryTabs:
    async def test_banned_shows_in_inactive_not_active(self, client, dir_env):
        """El vetado (user activo + is_banned) aparece en Inactivos, no en Activos."""
        active_ids, _ = await _list_ids(client, dir_env, True)
        inactive_ids, _ = await _list_ids(client, dir_env, False)

        assert dir_env["ids"]["banned"] not in active_ids, (
            "Un vetado no debe salir en la pestaña Activos ni en selectores"
        )
        assert dir_env["ids"]["banned"] in inactive_ids

    async def test_active_operator_still_in_active_tab(self, client, dir_env):
        active_ids, _ = await _list_ids(client, dir_env, True)
        assert dir_env["ids"]["active"] in active_ids

    async def test_blocked_still_in_inactive_tab(self, client, dir_env):
        inactive_ids, _ = await _list_ids(client, dir_env, False)
        assert dir_env["ids"]["blocked"] in inactive_ids

    async def test_ghost_excluded_from_inactive_tab(self, client, dir_env):
        """El fantasma (event_only) no contamina la pestaña Inactivos."""
        inactive_ids, _ = await _list_ids(client, dir_env, False)
        assert dir_env["ids"]["ghost"] not in inactive_ids

    async def test_inactive_total_counts_exclude_ghost(self, client, dir_env):
        """total de inactivos = vetado + bloqueado (fantasma excluido)."""
        _, data = await _list_ids(client, dir_env, False)
        assert data["total"] == 2

    async def test_default_list_excludes_banned_and_ghost(self, client, dir_env):
        """Default (is_active=true): solo el operador activo real."""
        r = await client.get("/api/operators/", headers=_hdrs(dir_env))
        assert r.status_code == 200
        ids = {it["id"] for it in r.json()["items"]}
        assert dir_env["ids"]["active"] in ids
        assert dir_env["ids"]["banned"] not in ids
        assert dir_env["ids"]["ghost"] not in ids


class TestSerialization:
    async def test_ghost_detail_serializes_without_email(self, client, dir_env):
        """GET de detalle de un usuario sin email no debe dar 500."""
        r = await client.get(
            f"/api/operators/{dir_env['ids']['ghost']}",
            headers=_hdrs(dir_env),
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] is None

    async def test_banned_item_reports_flags(self, client, dir_env):
        """El vetado en Inactivos llega con is_banned=True e is_active=True."""
        inactive_ids, data = await _list_ids(client, dir_env, False)
        item = next(it for it in data["items"]
                    if it["id"] == dir_env["ids"]["banned"])
        assert item["is_banned"] is True
        assert item["is_active"] is True