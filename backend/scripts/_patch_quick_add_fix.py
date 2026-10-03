# -*- coding: utf-8 -*-
"""Parche: fix 500 en quick-add (2/oct/2026).

Aplica 3 cambios a app/services/quick_add.py:
  1. Buscar usuario SOLO por document_number (el tipo guardado puede no ser
     canonico: importaciones Excel guardan "CEDULA"/"PA" mientras el
     formulario envia "CC"/"PP"). Antes: INSERT duplicado -> IntegrityError -> 500.
  2. admitted_by truncado a [:100] (la columna es String(100); [:200] causaba
     DataError en Postgres con nombres largos).
  3. try/except IntegrityError -> rollback + HTTPException 409 (doble-clic /
     concurrencia TOCTOU).

Y a app/services/operator_import.py:
  4. Mapping de _normalize_doc_type: agregar "CEDULA": "CC", "EXTRANJERIA": "CE",
     "PP": "PA", "PPT": "PPT" para que futuras importaciones guarden tipos
     canonicos.

Idempotente: si un cambio ya esta aplicado, lo detecta y continua.
"""
import io
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # backend/
QA = BASE / "app" / "services" / "quick_add.py"
OI = BASE / "app" / "services" / "operator_import.py"


def patch(path: Path, replacements: list, label: str) -> None:
    src = io.open(path, "r", encoding="utf-8").read()
    for old, new in replacements:
        if new in src:
            print(f"[{label}] ya aplicado: {old.strip().splitlines()[0][:60]}...")
            continue
        if old not in src:
            print(f"[{label}] ERROR: no se encontro el bloque buscado:")
            print("    " + old.strip().splitlines()[0][:80])
            sys.exit(1)
        src = src.replace(old, new, 1)
        print(f"[{label}] ok: {old.strip().splitlines()[0][:60]}...")
    io.open(path, "w", encoding="utf-8", newline="").write(src)


# ---------------- quick_add.py ----------------
QA_REPLACEMENTS = [
    # 1. import IntegrityError
    (
        "from fastapi import HTTPException\n"
        "from sqlalchemy import select, text\n"
        "from sqlalchemy.ext.asyncio import AsyncSession\n",
        "from fastapi import HTTPException\n"
        "from sqlalchemy import select, text\n"
        "from sqlalchemy.exc import IntegrityError\n"
        "from sqlalchemy.ext.asyncio import AsyncSession\n",
    ),
    # 2. docstring de reglas
    (
        "    Reglas:\n"
        "      1. Documento ya registrado como operador real \u2192 asignar existente\n"
        "         (mode=\"existing\"). NUNCA se crea un ghost sobre un documento real.\n",
        "    Reglas:\n"
        "      1. Documento ya registrado como operador real (con CUALQUIER tipo de\n"
        "         documento guardado, p. ej. \"CEDULA\" proveniente de importaciones\n"
        "         Excel o \"PA\") \u2192 asignar existente (mode=\"existing\"). NUNCA se\n"
        "         crea un ghost sobre un documento real. La b\u00fasqueda es SOLO por\n"
        "         n\u00famero: document_number es UNIQUE global en la BD.\n",
    ),
    # 3. busqueda solo por numero
    (
        "    # --- Buscar usuario existente por documento ---\n"
        "    res = await db.execute(\n"
        "        select(User).where(\n"
        "            User.document_number == doc_number,\n"
        "            User.document_type == doc_type,\n"
        "        )\n"
        "    )\n"
        "    existing_user = res.scalar_one_or_none()\n",
        "    # --- Buscar usuario existente por documento ---\n"
        "    # IMPORTANTE: buscar SOLO por n\u00famero. El \u00edndice ix_users_document_number\n"
        "    # es UNIQUE global (migraci\u00f3n inicial) y los tipos guardados no siempre\n"
        "    # son can\u00f3nicos: importaciones Excel guardan \"CEDULA\" o \"PA\" mientras\n"
        "    # el formulario env\u00eda \"CC\"/\"PP\". Filtrar tambi\u00e9n por tipo hac\u00eda que no\n"
        "    # se encontrara al usuario y el INSERT del ghost violara el UNIQUE \u2192 500.\n"
        "    res = await db.execute(\n"
        "        select(User).where(User.document_number == doc_number)\n"
        "    )\n"
        "    existing_user = res.scalar_one_or_none()\n",
    ),
    # 4. try/except IntegrityError + [:100]. Se hace en dos pasos:
    #    4a. abrir el try antes de la creacion del ghost
    (
        "    # --- Crear ghost si aplica ---\n"
        "    if operator is None:\n"
        "        if existing_user is None:\n",
        "    # --- Crear ghost si aplica ---\n"
        "    # IntegrityError \u2192 409: protege contra doble-clic del staff y contra\n"
        "    # dos agregando el mismo documento simult\u00e1neamente (carrera TOCTOU).\n"
        "    try:\n"
        "        if operator is None:\n"
        "            if existing_user is None:\n",
    ),
    #    4b. reindentar el bloque del ghost (+4 espacios)
    (
        "            ghost_user = User(\n"
        "                email=None,\n"
        "                password_hash=hash_password(secrets.token_urlsafe(24)),\n"
        "                first_name=first_name[:100],\n"
        "                last_name=(last_name or \"SIN APELLIDO\")[:100],\n"
        "                phone=None,\n"
        "                document_type=doc_type,\n"
        "                document_number=doc_number,\n"
        "                user_type=\"operator\",\n"
        "                role_id=role_id,\n"
        "                is_verified=False,\n"
        "                is_approved=False,\n"
        "                is_active=False,  # fantasma: no puede iniciar sesi\u00f3n\n"
        "            )\n"
        "            db.add(ghost_user)\n"
        "            await db.flush()\n"
        "            user = ghost_user\n"
        "        else:\n"
        "            # User sin perfil Operator (raro) \u2192 reutilizar user\n"
        "            user = existing_user\n"
        "\n"
        "        operator = Operator(\n"
        "            user_id=user.id,\n"
        "            event_only=True,  # \u2190 marca de purga\n"
        "        )\n"
        "        db.add(operator)\n"
        "        await db.flush()\n"
        "    else:\n"
        "        user = existing_user\n",
        "                ghost_user = User(\n"
        "                    email=None,\n"
        "                    password_hash=hash_password(secrets.token_urlsafe(24)),\n"
        "                    first_name=first_name[:100],\n"
        "                    last_name=(last_name or \"SIN APELLIDO\")[:100],\n"
        "                    phone=None,\n"
        "                    document_type=doc_type,\n"
        "                    document_number=doc_number,\n"
        "                    user_type=\"operator\",\n"
        "                    role_id=role_id,\n"
        "                    is_verified=False,\n"
        "                    is_approved=False,\n"
        "                    is_active=False,  # fantasma: no puede iniciar sesi\u00f3n\n"
        "                )\n"
        "                db.add(ghost_user)\n"
        "                await db.flush()\n"
        "                user = ghost_user\n"
        "            else:\n"
        "                # User sin perfil Operator (raro) \u2192 reutilizar user\n"
        "                user = existing_user\n"
        "\n"
        "            operator = Operator(\n"
        "                user_id=user.id,\n"
        "                event_only=True,  # \u2190 marca de purga\n"
        "            )\n"
        "            db.add(operator)\n"
        "            await db.flush()\n"
        "        else:\n"
        "            user = existing_user\n",
    ),
    #    4c. reindentar asignacion + [:100]
    (
        "    # --- Crear asignaci\u00f3n confirmada ---\n"
        "    now = datetime.now(timezone.utc)\n"
        "    assignment = EventAssignment(\n"
        "        event_id=event_id,\n"
        "        operator_id=operator.id,\n"
        "        role_id=role_id,\n"
        "        rate_applied=rate,\n"
        "        status=\"confirmed\",\n"
        "        stage=DEFAULT_STAGE,\n"
        "        confirmed_at=now,\n"
        "        is_active=True,\n"
        "        reminder_sent=False,\n"
        "        admitted_by=(admin_display or \"QUICK-ADD\")[:200],\n"
        "        programmed_by=\"Colab A&C\",\n"
        "    )\n"
        "    db.add(assignment)\n"
        "    await db.flush()\n",
        "        # --- Crear asignaci\u00f3n confirmada ---\n"
        "        now = datetime.now(timezone.utc)\n"
        "        assignment = EventAssignment(\n"
        "            event_id=event_id,\n"
        "            operator_id=operator.id,\n"
        "            role_id=role_id,\n"
        "            rate_applied=rate,\n"
        "            status=\"confirmed\",\n"
        "            stage=DEFAULT_STAGE,\n"
        "            confirmed_at=now,\n"
        "            is_active=True,\n"
        "            reminder_sent=False,\n"
        "            admitted_by=(admin_display or \"QUICK-ADD\")[:100],\n"
        "            programmed_by=\"Colab A&C\",\n"
        "        )\n"
        "        db.add(assignment)\n"
        "        await db.flush()\n",
    ),
    #    4d. reindentar recalculo + commit, y cerrar el try con except
    (
        "    # --- Recalcular quantity_confirmed del staff_need usado ---\n"
        "    if need is not None and role_id is not None:\n"
        "        cnt = await db.execute(\n"
        "            select(EventAssignment.id).where(\n"
        "                EventAssignment.event_id == event_id,\n"
        "                EventAssignment.role_id == role_id,\n"
        "                EventAssignment.stage == DEFAULT_STAGE,\n"
        "                EventAssignment.status == \"confirmed\",\n"
        "                EventAssignment.is_active.is_(True),\n"
        "            )\n"
        "        )\n"
        "        need.quantity_confirmed = len(cnt.all())\n"
        "        await db.flush()\n"
        "\n"
        "    await db.commit()\n",
        "        # --- Recalcular quantity_confirmed del staff_need usado ---\n"
        "        if need is not None and role_id is not None:\n"
        "            cnt = await db.execute(\n"
        "                select(EventAssignment.id).where(\n"
        "                    EventAssignment.event_id == event_id,\n"
        "                    EventAssignment.role_id == role_id,\n"
        "                    EventAssignment.stage == DEFAULT_STAGE,\n"
        "                    EventAssignment.status == \"confirmed\",\n"
        "                    EventAssignment.is_active.is_(True),\n"
        "                )\n"
        "            )\n"
        "            need.quantity_confirmed = len(cnt.all())\n"
        "            await db.flush()\n"
        "\n"
        "        await db.commit()\n"
        "    except IntegrityError:\n"
        "        await db.rollback()\n"
        "        raise HTTPException(\n"
        "            status_code=409,\n"
        "            detail=(\n"
        "                \"El documento ya fue registrado mientras se procesaba la \"\n"
        "                \"solicitud (posible doble clic). Verifique la lista e \"\n"
        "                \"intente de nuevo.\"\n"
        "            ),\n"
        "        )\n",
    ),
]

# ---------------- operator_import.py ----------------
OI_REPLACEMENTS = [
    (
        "        \"CEDULA DE CIUDADANIA\": \"CC\",\n"
        "        \"CEDULA CIUDADANIA\": \"CC\",\n"
        "        \"C.C.\": \"CC\",\n"
        "        \"CC\": \"CC\",\n",
        "        \"CEDULA DE CIUDADANIA\": \"CC\",\n"
        "        \"CEDULA CIUDADANIA\": \"CC\",\n"
        "        \"CEDULA\": \"CC\",\n"
        "        \"C.C.\": \"CC\",\n"
        "        \"CC\": \"CC\",\n",
    ),
    (
        "        \"CEDULA DE EXTRANJERIA\": \"CE\",\n"
        "        \"CEDULA EXTRANJERIA\": \"CE\",\n"
        "        \"C.E.\": \"CE\",\n"
        "        \"CE\": \"CE\",\n",
        "        \"CEDULA DE EXTRANJERIA\": \"CE\",\n"
        "        \"CEDULA EXTRANJERIA\": \"CE\",\n"
        "        \"EXTRANJERIA\": \"CE\",\n"
        "        \"C.E.\": \"CE\",\n"
        "        \"CE\": \"CE\",\n",
    ),
    (
        "        \"PASAPORTE\": \"PA\",\n"
        "        \"PA\": \"PA\",\n",
        "        \"PASAPORTE\": \"PA\",\n"
        "        \"PA\": \"PA\",\n"
        "        \"PP\": \"PA\",\n"
        "        \"PPT\": \"PPT\",\n",
    ),
]

if __name__ == "__main__":
    patch(QA, QA_REPLACEMENTS, "quick_add")
    patch(OI, OI_REPLACEMENTS, "operator_import")
    print("PATCH COMPLETO")