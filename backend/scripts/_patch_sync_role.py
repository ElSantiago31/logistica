# -*- coding: utf-8 -*-
"""Parche puntual: soporte de cambio de rol en check-in (sync.py)."""
import io, sys, pathlib

P = pathlib.Path(__file__).resolve().parent.parent / "app" / "routers" / "sync.py"
src = P.read_text(encoding="utf-8")

def rep(old, new, count=1):
    global src
    if old not in src:
        print(f"NO ENCONTRADO:\n{old[:120]}...")
        sys.exit(1)
    src = src.replace(old, new, count)

# 1) Helpers: _parse_log_notes + _apply_role_change (antes de _resolve_staff_access)
rep(
"""async def _resolve_staff_access(
    db: AsyncSession,
    user: User,
    event_id,
    allow_checkin: bool = True,
):""",
"""def _parse_log_notes(notes):
    \"\"\"Parsea las notas del AttendanceLog.

    Formato: 'sobrecupo:COORD | cambio_rol:OLD->NEW' (partes unidas por '|').
    Retorna (overquota_coord, role_change) - None en cada campo si no aplica.
    \"\"\"
    overquota_coord = None
    role_change = None
    for part in (notes or "").split("|"):
        part = part.strip()
        if part.startswith("sobrecupo:"):
            overquota_coord = part.split(":", 1)[1].strip() or None
        elif part.startswith("cambio_rol:"):
            role_change = part.split(":", 1)[1].strip() or None
    return overquota_coord, role_change


async def _apply_role_change(db: AsyncSession, assignment: EventAssignment, role_id):
    \"\"\"Aplica un cambio de rol al assignment (check-in).

    Retorna la nota para el log ('cambio_rol:OLD->NEW') o None si no hubo cambio.
    \"\"\"
    if not role_id or str(role_id) == str(assignment.role_id or ""):
        return None
    from app.models.roles import Role
    new_role = await db.get(Role, role_id)
    if not new_role:
        raise HTTPException(404, "Rol no encontrado")
    old_role = await db.get(Role, assignment.role_id) if assignment.role_id else None
    old_name = old_role.name if old_role else "Sin rol"
    assignment.role_id = new_role.id
    return f"cambio_rol:{old_name}->{new_role.name}"


async def _resolve_staff_access(
    db: AsyncSession,
    user: User,
    event_id,
    allow_checkin: bool = True,
):""")

# 2) offline-data: exponer role_id por assignment
rep(
"""            "role_name": role.name if role else "Operador",
            "status": assignment.status,""",
"""            "role_id": str(assignment.role_id) if assignment.role_id else None,
            "role_name": role.name if role else "Operador",
            "status": assignment.status,""")

# 3) sync batch offline: aplicar role_id del record
rep(
"""                        elif not assignment.admitted_by:
                            assignment.admitted_by = assignment.programmed_by
                        if can_set_uniform_batch:""",
"""                        elif not assignment.admitted_by:
                            assignment.admitted_by = assignment.programmed_by
                        rec_role_id = _to_uuid(rec.get("role_id"))
                        if rec_role_id and str(rec_role_id) != str(assignment.role_id or ""):
                            assignment.role_id = rec_role_id
                        if can_set_uniform_batch:""")

# 4) /attendance: parse de notas con role_change
rep(
"""    return {
        "event_id": str(event_id),
        "records": [
            {
                "id": str(log.id),
                "operator_name": f"{u.first_name} {u.last_name}",
                "check_in_time": str(log.check_in_time) if log.check_in_time else None,
                "check_out_time": str(log.check_out_time) if log.check_out_time else None,
                "method": log.check_in_method,
                "is_offline": log.is_offline,
                "overquota": (log.notes or "").startswith("sobrecupo:"),
                "coordinator": (
                    log.notes.split(":", 1)[1]
                    if (log.notes or "").startswith("sobrecupo:") else None
                ),
            }
            for log, op, u in rows
        ],
        "total": len(rows),
    }""",
"""    records = []
    for log, op, u in rows:
        overquota_coord, role_change = _parse_log_notes(log.notes)
        records.append({
            "id": str(log.id),
            "operator_name": f"{u.first_name} {u.last_name}",
            "check_in_time": str(log.check_in_time) if log.check_in_time else None,
            "check_out_time": str(log.check_out_time) if log.check_out_time else None,
            "method": log.check_in_method,
            "is_offline": log.is_offline,
            "overquota": overquota_coord is not None,
            "coordinator": overquota_coord,
            "role_change": role_change,
        })

    return {
        "event_id": str(event_id),
        "records": records,
        "total": len(rows),
    }""")

# 5) check_in: parsear role_id del payload
rep(
"""    force_overquota = bool(payload.get("force_overquota", False))
    overquota = False
    overquota_coord = None  # coordinador cuyo cupo se extendió (para el log)""",
"""    force_overquota = bool(payload.get("force_overquota", False))
    overquota = False
    overquota_coord = None  # coordinador cuyo cupo se extendió (para el log)
    role_id = _to_uuid(payload.get("role_id"))
    role_change_note = None  # "cambio_rol:OLD->NEW" si se cambió el rol""")

# 6) check_in reconciliado: aplicar rol también
rep(
"""                elif not assignment.admitted_by:
                    assignment.admitted_by = assignment.programmed_by
                try:
                    await db.commit()
                except Exception as exc:
                    await db.rollback()
                    logger.error("Error reconciliando check-in: %s", exc)""",
"""                elif not assignment.admitted_by:
                    assignment.admitted_by = assignment.programmed_by
                reconcile_note = await _apply_role_change(db, assignment, role_id)
                if reconcile_note:
                    parts = [p for p in (existing_log.notes or "").split("|") if p]
                    parts.append(reconcile_note)
                    existing_log.notes = "|".join(parts)
                try:
                    await db.commit()
                except Exception as exc:
                    await db.rollback()
                    logger.error("Error reconciliando check-in: %s", exc)""")

# 7) check_in flujo normal: aplicar rol antes de checked_in
rep(
"""            assignment.status = "checked_in"
            if shirt_number is not None:""",
"""            role_change_note = await _apply_role_change(db, assignment, role_id)

            assignment.status = "checked_in"
            if shirt_number is not None:""")

# 8) notas del log: combinar sobrecupo + cambio_rol
rep(
"""    # El log se construyo antes de validar el cupo del coordinador, asi que
    # el marcador de sobrecupo se asigna aqui (antes del commit).
    if overquota:
        log.notes = f"sobrecupo:{overquota_coord}\"""",
"""    # El log se construyo antes de validar el cupo del coordinador, asi que
    # los marcadores (sobrecupo / cambio de rol) se asignan aqui (antes del
    # commit). Se unen con '|' para poder combinar ambos.
    notes_parts = []
    if overquota:
        notes_parts.append(f"sobrecupo:{overquota_coord}")
    if role_change_note:
        notes_parts.append(role_change_note)
    if notes_parts:
        log.notes = "|".join(notes_parts)""")

# 9) CSV: helper _role_change_cell
rep(
"""        return "No"

    # Delimitador ';'""",
"""        return "No"

    def _role_change_cell(notes):
        \"\"\"'OLD -> NEW' si hubo cambio de rol en el check-in, '' si no.\"\"\"
        _, role_change = _parse_log_notes(notes)
        return role_change.replace("->", " -> ") if role_change else ""

    # Delimitador ';'""")

# 10) CSV: header con columna Cambio de Rol
rep(
"""        "Sobrecupo", "Rol", "Estado", "Método", "Offline", "Registrado Por",""",
"""        "Sobrecupo", "Rol", "Cambio de Rol", "Estado", "Método", "Offline", "Registrado Por",""")

# 11) CSV: fila con la celda de cambio de rol
rep(
"""            _sobrecupo_cell(log.notes),
            role.name if role else "",
            _pretty(assignment.status, STATUS_LABELS) if assignment else "",""",
"""            _sobrecupo_cell(log.notes),
            role.name if role else "",
            _role_change_cell(log.notes),
            _pretty(assignment.status, STATUS_LABELS) if assignment else "",""")

# 12) Nuevo endpoint PATCH /assignments/{id}/role (antes de /uniform)
rep(
"""@router.patch("/assignments/{assignment_id}/uniform")""",
"""@router.patch("/assignments/{assignment_id}/role")
async def change_assignment_role(
    assignment_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    \"\"\"Cambia el rol de un operador en el evento (antes o después del check-in).

    Actualiza EventAssignment.role_id y, si ya hay check-in, anota el cambio
    en el AttendanceLog existente (notes: 'cambio_rol:OLD->NEW') para que
    aparezca en el log de ingresos y en el CSV.
    \"\"\"
    from app.models.roles import Role

    new_role_id = _to_uuid(payload.get("role_id"))
    if not new_role_id:
        raise HTTPException(400, "role_id requerido")

    assignment = await db.get(EventAssignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Asignación no encontrada")

    await _resolve_staff_access(db, user, assignment.event_id)

    new_role = await db.get(Role, new_role_id)
    if not new_role:
        raise HTTPException(404, "Rol no encontrado")

    old_role = await db.get(Role, assignment.role_id) if assignment.role_id else None
    old_name = old_role.name if old_role else "Sin rol"

    if assignment.role_id and str(assignment.role_id) == str(new_role_id):
        return {
            "status": "unchanged",
            "assignment_id": str(assignment.id),
            "old_role": old_name,
            "new_role": new_role.name,
        }

    assignment.role_id = new_role_id

    # Anotar en el log de asistencia si ya hizo check-in
    role_note = f"cambio_rol:{old_name}->{new_role.name}"
    if assignment.status == "checked_in":
        existing = await db.execute(
            select(AttendanceLog).where(
                AttendanceLog.event_id == assignment.event_id,
                AttendanceLog.operator_id == assignment.operator_id,
            )
        )
        log = existing.scalar_one_or_none()
        if log:
            parts = [p for p in (log.notes or "").split("|") if p]
            parts.append(role_note)
            log.notes = "|".join(parts)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        safe_http_error(
            status_code=500,
            client_message="Error interno del servidor",
            log_detail="Error al cambiar rol de asignación",
            exc=exc,
        )

    # --- Audit log ---
    try:
        from app.services.events import _add_audit_log
        await _add_audit_log(
            db,
            event_id=assignment.event_id,
            user_id=user.id,
            action="role_change",
            changes={
                "assignment_id": str(assignment.id),
                "operator_id": str(assignment.operator_id),
                "old_role": old_name,
                "new_role": new_role.name,
                "reason": (payload.get("reason") or "").strip() or "Cambio manual en check-in",
            },
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("No se pudo registrar audit log de cambio de rol: %s", exc)

    # --- Notificar por WebSocket (cambio de rol) ---
    try:
        await ws_manager.publish_broadcast(
            str(assignment.event_id),
            "role_change",
            {
                "assignment_id": str(assignment.id),
                "old_role": old_name,
                "new_role": new_role.name,
                "by": f"{user.first_name} {user.last_name}",
            },
        )
    except Exception as exc:
        logger.warning("[ws] no se pudo emitir role_change: %s", exc)

    return {
        "status": "role_changed",
        "assignment_id": str(assignment.id),
        "old_role": old_name,
        "new_role": new_role.name,
        "message": f"Rol cambiado de {old_name} a {new_role.name}",
    }


@router.patch("/assignments/{assignment_id}/uniform")""")

# 13) checkin-status: incluir role_id/role_name por assignment
rep(
"""    # --- Fase 1: status + uniform por asignación ---
    result = await db.execute(
        select(EventAssignment)
        .where(EventAssignment.event_id == event_id)
    )
    assignments = result.scalars().all()""",
"""    # --- Fase 1: status + uniform + rol por asignación ---
    from app.models.roles import Role
    result = await db.execute(
        select(EventAssignment, Role)
        .outerjoin(Role, Role.id == EventAssignment.role_id)
        .where(EventAssignment.event_id == event_id)
    )
    assignment_rows = result.all()""")

# 14) checkin-status: recent_activity con role_change
rep(
"""        for log, op in recent_result.all():
            recent_activity.append({
                "operator_name": f"{op.user.first_name} {op.user.last_name}" if op.user else "—",
                "check_in_time": log.check_in_time.isoformat() if log.check_in_time else None,
                "method": log.check_in_method,
                "overquota": (log.notes or "").startswith("sobrecupo:"),
                "coordinator": (
                    log.notes.split(":", 1)[1]
                    if (log.notes or "").startswith("sobrecupo:") else None
                ),
            })""",
"""        for log, op in recent_result.all():
            overquota_coord, role_change = _parse_log_notes(log.notes)
            recent_activity.append({
                "operator_name": f"{op.user.first_name} {op.user.last_name}" if op.user else "—",
                "check_in_time": log.check_in_time.isoformat() if log.check_in_time else None,
                "method": log.check_in_method,
                "overquota": overquota_coord is not None,
                "coordinator": overquota_coord,
                "role_change": role_change,
            })""")

# 15) checkin-status: assignments con role
rep(
"""        "assignments": [
            {
                "id": str(a.id),
                "status": a.status,
                "shirt_number": a.shirt_number,
                "jacket_number": a.jacket_number,
                "cap_number": a.cap_number,
            }
            for a in assignments
        ],
    }""",
"""        "assignments": [
            {
                "id": str(a.id),
                "status": a.status,
                "shirt_number": a.shirt_number,
                "jacket_number": a.jacket_number,
                "cap_number": a.cap_number,
                "role_id": str(a.role_id) if a.role_id else None,
                "role_name": r.name if r else None,
            }
            for a, r in assignment_rows
        ],
    }""")

P.write_text(src, encoding="utf-8")
print("OK: parche aplicado")