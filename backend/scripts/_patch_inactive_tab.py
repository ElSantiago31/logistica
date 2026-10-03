# -*- coding: utf-8 -*-
"""Parche: pestaña Inactivos del directorio de operadores (admin).

Problemas detectados:
1. Los VETADOS (Operator.is_banned=True, creados vía POST /api/bans) mantienen
   User.is_active=True, así que nunca aparecían en la pestaña "Inactivos"
   (is_active=false) del directorio de operadores.
2. Los FANTASMAS de Incorporación Rápida (is_active=False, email=None,
   event_only=True) contaminaban la pestaña Inactivos y rompían la
   serialización (OperatorResponse.email era str obligatorio → error 500).

Solución:
- schemas/operators.py: OperatorResponse.email pasa a Optional (fantasmas
  sin email ya no rompen la serialización).
- services/operators.py::get_operators: estado combinado:
      activo   = User.is_active=True AND sin veto (Operator.is_banned=False)
      inactivo = User.is_active=False OR veto, excluyendo fantasmas (event_only)
  Esto también excluye a los vetados de los selectores de operadores para
  eventos (que consultan con is_active=true): no se debe poder asignar a
  alguien con veto activo.
- templates/admin/operators.html: el badge y el fondo de fila reflejan el
  estado combinado (un vetado ya no se muestra como "Activo" en verde).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app"


def patch(rel: str, old: str, new: str, *, count: int = 1):
    p = ROOT / rel
    src = p.read_text(encoding="utf-8")
    found = src.count(old)
    assert found == count, (
        f"{rel}: patrón encontrado {found}x (esperado {count}): {old[:70]!r}"
    )
    p.write_text(src.replace(old, new), encoding="utf-8")
    print(f"OK  {rel}: {old[:48]!r}")


# ─── 1. Schema: tolerar email nulo (fantasmas / bloqueados) ──────────────────
patch(
    "schemas/operators.py",
    "    id: uuid.UUID\n    email: str\n",
    "    id: uuid.UUID\n    email: Optional[str] = None\n",
)

# ─── 2. Servicio: estado combinado activo/inactivo en get_operators ─────────
patch(
    "services/operators.py",
    "    from sqlalchemy.orm import joinedload\n"
    "    from sqlalchemy import or_, func as sa_func\n"
    "\n"
    "    # Base query for selecting\n"
    "    query = select(User).where(\n"
    "        User.user_type == \"operator\",\n"
    "        User.is_active == is_active\n"
    "    ).options(",
    "    from sqlalchemy.orm import joinedload\n"
    "    from sqlalchemy import or_, and_, func as sa_func\n"
    "\n"
    "    # Estado combinado para el directorio (pestañas Activos/Inactivos):\n"
    "    #   activo   → User.is_active=True y sin veto (Operator.is_banned=False)\n"
    "    #   inactivo → User.is_active=False o con veto (Operator.is_banned=True)\n"
    "    # Los fantasmas de Incorporación Rápida (event_only, sin email) se\n"
    "    # excluyen de inactivos: son registros internos del ciclo del evento.\n"
    "    banned_exists = select(Operator.id).where(\n"
    "        Operator.user_id == User.id,\n"
    "        Operator.is_banned == True,\n"
    "    ).exists()\n"
    "    ghost_exists = select(Operator.id).where(\n"
    "        Operator.user_id == User.id,\n"
    "        Operator.event_only == True,\n"
    "    ).exists()\n"
    "\n"
    "    if is_active:\n"
    "        state_filter = and_(User.is_active == True, ~banned_exists)\n"
    "    else:\n"
    "        state_filter = and_(\n"
    "            or_(User.is_active == False, banned_exists),\n"
    "            ~ghost_exists,\n"
    "        )\n"
    "\n"
    "    # Base query for selecting\n"
    "    query = select(User).where(\n"
    "        User.user_type == \"operator\",\n"
    "        state_filter,\n"
    "    ).options(",
)

patch(
    "services/operators.py",
    "    # Base count\n"
    "    count_query = select(func.count()).select_from(User).where(\n"
    "        User.user_type == \"operator\",\n"
    "        User.is_active == is_active\n"
    "    )",
    "    # Base count\n"
    "    count_query = select(func.count()).select_from(User).where(\n"
    "        User.user_type == \"operator\",\n"
    "        state_filter,\n"
    "    )",
)

# ─── 3. UI: badge/botón según estado combinado ───────────────────────────────
# Cards (multilínea)
patch(
    "templates/admin/operators.html",
    "const statusBadge = op.is_active\n",
    "const statusBadge = (op.is_active && !op.is_banned)\n",
)
# Tabla (una línea)
patch(
    "templates/admin/operators.html",
    "const statusBadge = op.is_active ? '<span",
    "const statusBadge = (op.is_active && !op.is_banned) ? '<span",
)
# Fondo rojo de tarjeta (cards)
patch(
    "templates/admin/operators.html",
    "const blocked = !op.is_active;",
    "const blocked = !op.is_active || op.is_banned;",
)
# Fondo rojo de fila (tabla)
patch(
    "templates/admin/operators.html",
    "'+(op.is_active?'':'bg-red-50/50')+'",
    "'+(op.is_active && !op.is_banned?'':'bg-red-50/50')+'",
)
# Botón eliminar solo para activos reales (no vetados)
patch(
    "templates/admin/operators.html",
    "+(op.is_active ? '<button onclick=\"deleteOp(",
    "+(op.is_active && !op.is_banned ? '<button onclick=\"deleteOp(",
)

print("\nParche aplicado.")