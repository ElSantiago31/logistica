#!/usr/bin/env python
"""Diagnóstico de planilla: ejecuta cada paso y reporta dónde falla.

Uso:
    docker exec logistica_backend python -m scripts.diag_planilla <event_id>

Ejemplo:
    docker exec logistica_backend python -m scripts.diag_planilla c96ca27a-c16b-49fd-9335-0b07e548085e
"""
import asyncio
import sys
import traceback
import uuid

# Colores ANSI para mejor legibilidad en consola
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg: str, data=None):
    extra = f" ({data})" if data is not None else ""
    print(f"  {GREEN}✓ {msg}{RESET}{extra}")


def fail(msg: str, exc: Exception):
    print(f"  {RED}✗ {msg}{RESET}")
    print(f"    {RED}Error: {exc}{RESET}")
    print(f"    {YELLOW}Traceback:{RESET}")
    tb_lines = traceback.format_exc().splitlines()
    for line in tb_lines:
        print(f"      {line}")


async def main(event_id_str: str):
    event_id = uuid.UUID(event_id_str)
    errors = []

    print(f"\n{BOLD}═══ DIAGNÓSTICO DE PLANILLA ═══{RESET}")
    print(f"Event ID: {event_id}\n")

    # Imports diferidos para no fallar si hay errores de import
    from app.database import AsyncSessionLocal
    from sqlalchemy import select
    from app.models.events import Event, EventAssignment
    from app.models.operators import Operator
    from app.models.users import User
    from app.models.roles import Role
    from app.models.incidents import OperatorIncident, OperatorBan

    async with AsyncSessionLocal() as db:
        # Paso 1: obtener evento
        print(f"{BOLD}[1/8] Obtener evento{RESET}")
        try:
            event = await db.get(Event, event_id)
            if not event:
                print(f"  {RED}✗ Evento no encontrado{RESET}")
                return
            ok("Evento encontrado", f"name={event.name!r}")
        except Exception as exc:
            fail("get_event", exc)
            errors.append("get_event")
            return

        # Paso 2: consultar operadores checked_in
        print(f"\n{BOLD}[2/8] Consultar operadores checked_in{RESET}")
        try:
            result = await db.execute(
                select(EventAssignment, Operator, User, Role)
                .join(Operator, Operator.id == EventAssignment.operator_id)
                .join(User, User.id == Operator.user_id)
                .outerjoin(Role, Role.id == EventAssignment.role_id)
                .where(
                    EventAssignment.event_id == event_id,
                    EventAssignment.status == "checked_in",
                )
            )
            rows = result.all()
            ok("Query exitosa", f"{len(rows)} operadores")
        except Exception as exc:
            fail("query_operators", exc)
            errors.append("query_operators")
            return

        # Paso 3: build_coordinator_map
        print(f"\n{BOLD}[3/8] Construir mapa de coordinadores{RESET}")
        area_to_coord = {}
        general_coord = None
        try:
            from app.routers.payroll import _build_coordinator_map
            area_to_coord, general_coord = await _build_coordinator_map(db, event_id)
            ok(
                "Mapa construido",
                f"{len(area_to_coord)} áreas, general={general_coord[0] if general_coord else None!r}",
            )
        except Exception as exc:
            fail("build_coordinator_map", exc)
            errors.append("build_coordinator_map")

        # Paso 4: consultar incidencias
        print(f"\n{BOLD}[4/8] Consultar incidencias{RESET}")
        try:
            inc_result = await db.execute(
                select(OperatorIncident.operator_id)
                .where(OperatorIncident.event_id == event_id)
                .distinct()
            )
            ops_with_incident = {str(oid) for (oid,) in inc_result.all()}
            ok("Query exitosa", f"{len(ops_with_incident)} con incidencias")
        except Exception as exc:
            fail("query_incidents", exc)
            errors.append("query_incidents")

        # Paso 5: consultar vetos
        print(f"\n{BOLD}[5/8] Consultar vetos{RESET}")
        try:
            ban_result = await db.execute(
                select(OperatorBan.operator_id)
                .where(OperatorBan.is_active.is_(True))
                .distinct()
            )
            banned_ops = {str(oid) for (oid,) in ban_result.all()}
            ok("Query exitosa", f"{len(banned_ops)} vetados")
        except Exception as exc:
            fail("query_bans", exc)
            errors.append("query_bans")

        # Paso 6: construir lista de operadores
        print(f"\n{BOLD}[6/8] Construir lista de operadores{RESET}")
        operators = []
        try:
            for assignment, operator, op_user, role in rows:
                coord_name = assignment.programmed_by or assignment.admitted_by
                if not coord_name:
                    coord_name = general_coord[0] if general_coord else "Sin asignar"
                    if role and role.area and role.area in area_to_coord:
                        coord_name = area_to_coord[role.area][0]

                operators.append({
                    "first_name": op_user.first_name or "",
                    "last_name": op_user.last_name or "",
                    "full_name": f"{op_user.first_name} {op_user.last_name}",
                    "document_number": op_user.document_number or "",
                    "coordinator_name": coord_name,
                    "role_name": role.name if role else "Operador",
                })
            ok("Lista construida", f"{len(operators)} operadores")
        except Exception as exc:
            fail("build_operators_list", exc)
            errors.append("build_operators_list")
            return

        # Mostrar primeros 5 operadores como muestra
        if operators:
            print(f"\n  {BOLD}Muestra (primeros 5):{RESET}")
            for op in operators[:5]:
                print(f"    - {op['first_name']} {op['last_name']} | "
                      f"doc={op['document_number']} | coord={op['coordinator_name']}")

        # Paso 7: generar Excel
        print(f"\n{BOLD}[7/8] Generar Excel (.xlsx){RESET}")
        try:
            from app.services.planilla_excel import generate_planilla_xlsx
            xlsx_bytes = generate_planilla_xlsx(
                event_name=event.name,
                event_date=event.start_date,
                event_location=event.location,
                operators=operators,
                group_by="coordinator",
                sort_by="lastname",
            )
            ok("Excel generado", f"{len(xlsx_bytes)} bytes")
        except Exception as exc:
            fail("generate_xlsx", exc)
            errors.append("generate_xlsx")

        # Paso 8: generar PDF
        print(f"\n{BOLD}[8/8] Generar PDF{RESET}")
        try:
            from app.services.planilla_pdf import generate_planilla_pdf
            pdf_bytes = generate_planilla_pdf(
                event_name=event.name,
                event_date=event.start_date,
                event_location=event.location,
                operators=operators,
                group_by="coordinator",
                sort_by="lastname",
            )
            ok("PDF generado", f"{len(pdf_bytes)} bytes")
        except Exception as exc:
            fail("generate_pdf", exc)
            errors.append("generate_pdf")

    # Resumen final
    print(f"\n{BOLD}═══ RESUMEN ═══{RESET}")
    if errors:
        print(f"  {RED}❌ FALLARON {len(errors)} pasos: {', '.join(errors)}{RESET}")
    else:
        print(f"  {GREEN}✅ Todos los pasos pasaron correctamente{RESET}")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Uso: python -m scripts.diag_planilla <event_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))