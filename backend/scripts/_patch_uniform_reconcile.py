"""Parche one-off: persistir indumentaria del payload en el camino
"reconcile" del check-in (operador ya registrado / assignment no checked_in).

Antes: el reconcile solo forzaba checked_in y resolvia coordinador/rol,
ignorando shirt/jacket/cap que venian en el payload del check-in.
Ahora: aplica la misma validacion de conflictos que /uniform y persiste
los campos no-null, tanto si el assignment se reconcilia como si ya estaba
checked_in (form llenado de nuevo). Ejecutar una sola vez y borrar.
"""
import io

PATH = r"backend/app/routers/sync.py"

OLD = '''        if assignment_id:
            assignment = await db.get(EventAssignment, assignment_id)
            if assignment and assignment.status != "checked_in":
                assignment.status = "checked_in"
                # Resolver coordinador (misma lógica del flujo normal)
                if coordinator:
                    assignment.admitted_by = coordinator
                    if not assignment.programmed_by:
                        assignment.programmed_by = coordinator
                elif not assignment.admitted_by:
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
                    logger.error("Error reconciliando check-in: %s", exc)
        return {"status": "checked_in", "log_id": str(existing_log.id), "reconciled": True}'''

NEW = '''        if assignment_id:
            assignment = await db.get(EventAssignment, assignment_id)
            if assignment:
                needs_commit = False
                if assignment.status != "checked_in":
                    assignment.status = "checked_in"
                    needs_commit = True
                    # Resolver coordinador (misma lógica del flujo normal)
                    if coordinator:
                        assignment.admitted_by = coordinator
                        if not assignment.programmed_by:
                            assignment.programmed_by = coordinator
                    elif not assignment.admitted_by:
                        assignment.admitted_by = assignment.programmed_by
                    reconcile_note = await _apply_role_change(db, assignment, role_id)
                    if reconcile_note:
                        parts = [p for p in (existing_log.notes or "").split("|") if p]
                        parts.append(reconcile_note)
                        existing_log.notes = "|".join(parts)
                # Guardar también la indumentaria diligenciada que viene en el
                # payload del check-in (mismo criterio del flujo normal): aplica
                # tanto al reconcile (status != checked_in) como cuando ya estaba
                # registrado y el formulario se llenó de nuevo. Campos null no
                # sobrescriben valores existentes.
                if shirt_number is not None or jacket_number is not None or cap_number is not None:
                    uniform_conflict = await _check_uniform_conflicts(
                        db, event_id, assignment_id,
                        shirt_number, jacket_number, cap_number,
                    )
                    if uniform_conflict:
                        await db.rollback()
                        raise HTTPException(409, uniform_conflict)
                    if shirt_number is not None and assignment.shirt_number != (shirt_number or None):
                        assignment.shirt_number = shirt_number or None
                        needs_commit = True
                    if jacket_number is not None and assignment.jacket_number != (jacket_number or None):
                        assignment.jacket_number = jacket_number or None
                        needs_commit = True
                    if cap_number is not None and assignment.cap_number != (cap_number or None):
                        assignment.cap_number = cap_number or None
                        needs_commit = True
                if needs_commit:
                    try:
                        await db.commit()
                    except Exception as exc:
                        await db.rollback()
                        logger.error("Error reconciliando check-in: %s", exc)
        return {"status": "checked_in", "log_id": str(existing_log.id), "reconciled": True}'''


def main():
    s = io.open(PATH, encoding="utf-8").read()
    if "needs_commit" in s:
        print("YA APLICADO")
        return
    if OLD not in s:
        raise SystemExit("ERROR: bloque SEARCH no encontrado")
    io.open(PATH, "w", encoding="utf-8", newline="").write(s.replace(OLD, NEW, 1))
    ok = "needs_commit" in io.open(PATH, encoding="utf-8").read()
    print("APLICADO" if ok else "FALLO VERIFICACION")


if __name__ == "__main__":
    main()