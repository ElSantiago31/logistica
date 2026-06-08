"""Payroll router — evaluations, payroll calculation, and digital signatures."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.events import Event, EventAssignment
from app.models.operators import Operator
from app.models.payroll import Evaluation, Payroll, Signature
from app.models.sync import AttendanceLog
from app.models.users import User

router = APIRouter(prefix="/api/payroll", tags=["Payroll"])


# ============================================================
# EVALUATIONS
# ============================================================

@router.post("/evaluations")
async def create_evaluation(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create post-event evaluation for an operator."""
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")

    scores = [
        payload.get("punctuality_score", 3),
        payload.get("performance_score", 3),
        payload.get("appearance_score", 3),
        payload.get("attitude_score", 3),
    ]
    overall = round(sum(scores) / len(scores), 2)

    evaluation = Evaluation(
        event_id=payload["event_id"],
        operator_id=payload["operator_id"],
        evaluated_by=user.id,
        punctuality_score=scores[0],
        performance_score=scores[1],
        appearance_score=scores[2],
        attitude_score=scores[3],
        overall_score=overall,
        comments=payload.get("comments"),
        would_hire_again=payload.get("would_hire_again", True),
    )
    db.add(evaluation)
    await db.commit()

    return {"id": str(evaluation.id), "overall_score": overall}


@router.get("/evaluations/{event_id}")
async def get_evaluations(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get all evaluations for an event."""
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")

    result = await db.execute(
        select(Evaluation, Operator, User)
        .join(Operator, Operator.id == Evaluation.operator_id)
        .join(User, User.id == Operator.user_id)
        .where(Evaluation.event_id == event_id)
    )
    rows = result.all()

    return {
        "evaluations": [
            {
                "id": str(evl.id),
                "operator_name": f"{u.first_name} {u.last_name}",
                "punctuality": evl.punctuality_score,
                "performance": evl.performance_score,
                "appearance": evl.appearance_score,
                "attitude": evl.attitude_score,
                "overall": evl.overall_score,
                "would_hire": evl.would_hire_again,
                "comments": evl.comments,
            }
            for evl, op, u in rows
        ],
        "total": len(rows),
    }


# ============================================================
# PAYROLL CALCULATION
# ============================================================

@router.post("/events/{event_id}/calculate")
async def calculate_payroll(
    event_id: uuid.UUID,
    rate_per_hour: float = Query(18000.0, description="Tarifa por hora"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Calculate payroll for all checked-in operators in an event."""
    if user.user_type not in ("admin", "superadmin"):
        raise HTTPException(403, "Sin permisos")

    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")

    # Get attendance logs
    result = await db.execute(
        select(AttendanceLog).where(AttendanceLog.event_id == event_id)
    )
    attendance = result.scalars().all()

    calculated = 0
    for att in attendance:
        # Check if payroll already exists
        existing = await db.execute(
            select(Payroll).where(
                Payroll.event_id == event_id,
                Payroll.operator_id == att.operator_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        # Calculate hours
        hours = 8.0  # Default full day
        if att.check_in_time and att.check_out_time:
            delta = att.check_out_time - att.check_in_time
            hours = round(delta.total_seconds() / 3600, 2)

        total = hours * rate_per_hour
        deductions = total * 0.04  # 4% retención simplificada

        payroll = Payroll(
            event_id=event_id,
            operator_id=att.operator_id,
            assignment_id=att.assignment_id,
            hours_worked=hours,
            rate_per_hour=rate_per_hour,
            total_amount=total,
            deductions=deductions,
            net_amount=round(total - deductions, 2),
            status="calculated",
        )
        db.add(payroll)
        calculated += 1

    await db.commit()
    return {"calculated": calculated, "rate_per_hour": rate_per_hour}


@router.get("/events/{event_id}/payroll")
async def get_event_payroll(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get payroll for an event."""
    if user.user_type not in ("admin", "superadmin"):
        raise HTTPException(403, "Sin permisos")

    result = await db.execute(
        select(Payroll, Operator, User)
        .join(Operator, Operator.id == Payroll.operator_id)
        .join(User, User.id == Operator.user_id)
        .where(Payroll.event_id == event_id)
    )
    rows = result.all()

    total_payroll = sum(p.net_amount for p, _, _ in rows)

    return {
        "event_id": str(event_id),
        "total_payroll": total_payroll,
        "records": [
            {
                "id": str(p.id),
                "operator_name": f"{u.first_name} {u.last_name}",
                "document_number": u.document_number,
                "hours": p.hours_worked,
                "rate": p.rate_per_hour,
                "total": p.total_amount,
                "deductions": p.deductions,
                "net": p.net_amount,
                "status": p.status,
                "has_signature": p.signature is not None,
            }
            for p, op, u in rows
        ],
        "total_records": len(rows),
    }


@router.patch("/payroll/{payroll_id}/status")
async def update_payroll_status(
    payroll_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update payroll record status and payment info."""
    if user.user_type not in ("admin", "superadmin"):
        raise HTTPException(403, "Sin permisos")

    payroll = await db.get(Payroll, payroll_id)
    if not payroll:
        raise HTTPException(404, "Registro no encontrado")

    new_status = payload.get("status")
    if new_status:
        payroll.status = new_status
    if payload.get("payment_method"):
        payroll.payment_method = payload["payment_method"]
    if payload.get("payment_reference"):
        payroll.payment_reference = payload["payment_reference"]
    if new_status == "paid":
        payroll.paid_at = datetime.utcnow().isoformat()

    await db.commit()
    return {"status": payroll.status}


# ============================================================
# SIGNATURES
# ============================================================

@router.post("/payroll/{payroll_id}/sign")
async def sign_payroll(
    payroll_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Record digital signature for a payroll record."""
    payroll = await db.get(Payroll, payroll_id)
    if not payroll:
        raise HTTPException(404, "Registro no encontrado")

    # Check if already signed
    existing = await db.execute(
        select(Signature).where(Signature.payroll_id == payroll_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Ya firmado")

    signature = Signature(
        payroll_id=payroll_id,
        operator_id=payroll.operator_id,
        signature_data=payload["signature_data"],
        signature_hash=payload["signature_hash"],
        signed_at=datetime.utcnow().isoformat(),
        ip_address=payload.get("ip_address"),
        device_info=payload.get("device_info"),
        is_offline=payload.get("is_offline", False),
    )
    db.add(signature)

    payroll.status = "signed"
    await db.commit()

    return {"signed": True, "signature_id": str(signature.id)}