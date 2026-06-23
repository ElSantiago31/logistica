"""Reports router — CSV exports for attendance, payroll, and evaluations."""
import uuid
import io
import csv
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.events import Event
from app.models.operators import Operator
from app.models.payroll import PayrollRecord, Evaluation
from app.models.sync import AttendanceLog
from app.models.users import User

router = APIRouter(prefix="/api/reports", tags=["Reports"])


def _csv_response(data, filename, fieldnames):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(data)
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/events/{event_id}/attendance.csv")
async def export_attendance_csv(event_id: uuid.UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403)
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(404)
    result = await db.execute(
        select(AttendanceLog, Operator, User)
        .join(Operator, Operator.id == AttendanceLog.operator_id)
        .join(User, User.id == Operator.user_id)
        .where(AttendanceLog.event_id == event_id)
    )
    rows = result.all()
    data = [{"Nombre": f"{u.first_name} {u.last_name}", "Cedula": u.document_number or "",
             "Telefono": u.phone or "", "Check-in": str(log.check_in_time) if log.check_in_time else "",
             "Check-out": str(log.check_out_time) if log.check_out_time else "",
             "Metodo": log.check_in_method, "Offline": "Si" if log.is_offline else "No"}
            for log, op, u in rows]
    fn = f"asistencia_{event.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(data, fn, ["Nombre", "Cedula", "Telefono", "Check-in", "Check-out", "Metodo", "Offline"])


@router.get("/events/{event_id}/payroll.csv")
async def export_payroll_csv(event_id: uuid.UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if user.user_type not in ("admin", "superadmin"):
        raise HTTPException(403)
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(404)
    result = await db.execute(
        select(PayrollRecord, Operator, User)
        .join(Operator, Operator.id == PayrollRecord.operator_id)
        .join(User, User.id == Operator.user_id)
        .where(PayrollRecord.event_id == event_id)
    )
    rows = result.all()
    data = [{"Nombre": f"{u.first_name} {u.last_name}", "Cedula": u.document_number or "",
             "Cargo": p.role_name_snapshot or "", "Monto": p.payment_amount,
             "Estado": p.status, "Factura": p.invoice_number or "",
             "Firmado": "Si" if p.signature_data else "No"}
            for p, op, u in rows]
    total = sum(d["Monto"] for d in data)
    data.append({"Nombre": "TOTAL", "Cedula": "", "Cargo": "", "Monto": total, "Estado": "", "Factura": "", "Firmado": ""})
    fn = f"nomina_{event.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(data, fn, ["Nombre", "Cedula", "Cargo", "Monto", "Estado", "Factura", "Firmado"])


@router.get("/events/{event_id}/evaluations.csv")
async def export_evaluations_csv(event_id: uuid.UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403)
    result = await db.execute(
        select(Evaluation, Operator, User)
        .join(Operator, Operator.id == Evaluation.operator_id)
        .join(User, User.id == Operator.user_id)
        .where(Evaluation.event_id == event_id)
    )
    rows = result.all()
    data = [{"Nombre": f"{u.first_name} {u.last_name}", "Puntualidad": evl.punctuality_score,
             "Desempeno": evl.performance_score, "Presentacion": evl.appearance_score,
             "Actitud": evl.attitude_score, "Promedio": evl.overall_score,
             "Recontratar": "Si" if evl.would_hire_again else "No", "Comentarios": evl.comments or ""}
            for evl, op, u in rows]
    fn = f"evaluaciones_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(data, fn, ["Nombre", "Puntualidad", "Desempeno", "Presentacion", "Actitud", "Promedio", "Recontratar", "Comentarios"])


@router.get("/operators.csv")
async def export_operators_csv(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if user.user_type not in ("admin", "superadmin"):
        raise HTTPException(403)
    result = await db.execute(select(Operator, User).join(User, User.id == Operator.user_id))
    rows = result.all()
    data = [{"Nombre": f"{u.first_name} {u.last_name}", "Cedula": u.document_number or "",
             "Telefono": u.phone or "", "Email": u.email or "", "Estado": u.user_status}
            for op, u in rows]
    fn = f"operadores_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(data, fn, ["Nombre", "Cedula", "Telefono", "Email", "Estado"])