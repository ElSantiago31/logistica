"""Referrals router — SuperAdmin management of referral codes.

Endpoints:
- GET  /api/referrals/stats          → métricas globales del módulo
- GET  /api/referrals/codes          → lista de códigos con métricas por referente
- POST /api/referrals/codes          → generar código para un operador
- PATCH /api/referrals/codes/{id}    → habilitar/deshabilitar código
- GET  /api/referrals/{operator_id}  → detalle de un referente (métricas + referidos)
- GET  /api/referrals/export         → exportar a Excel
- GET  /admin/referrals              → página SuperAdmin (SSR + fetch)
"""
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_superadmin
from app.models.operators import Operator
from app.models.referrals import Referral, ReferralCode
from app.models.users import User
from app.services import referrals as referral_service
from app.services.referrals import ReferralError

router = APIRouter(prefix="/api/referrals", tags=["Referrals"])
templates = Jinja2Templates(directory="app/templates")


def _operator_label(user: User | None) -> str:
    if not user:
        return "—"
    return f"{user.first_name} {user.last_name}".strip() or user.email


async def _resolve_operator(db: AsyncSession, some_id: uuid.UUID) -> Operator:
    """Resuelve un operador desde su Operator.id O el User.id asociado.

    El buscador del frontend usa /api/operators (items con User.id) mientras
    el módulo de referidos opera con Operator.id; aceptar ambos evita 404.
    """
    operator = await db.get(Operator, some_id)
    if operator:
        return operator
    operator = await db.scalar(select(Operator).where(Operator.user_id == some_id))
    if not operator:
        raise HTTPException(status_code=404, detail="Operador no encontrado")
    return operator


async def _code_with_metrics(db: AsyncSession, code: ReferralCode) -> dict:
    """Serializa un ReferralCode con datos del referente y métricas."""
    referrer = await db.get(Operator, code.operator_id)
    user = await db.get(User, referrer.user_id) if referrer and referrer.user_id else None
    metrics = await referral_service.get_referrer_metrics(db, code.operator_id)
    return {
        "id": str(code.id),
        "code": code.code,
        "operator_id": str(code.operator_id),
        "operator_user_id": str(referrer.user_id) if referrer and referrer.user_id else None,
        "operator_name": _operator_label(user),
        "operator_document": user.document_number if user else None,
        "is_active": code.is_active,
        "created_at": str(code.created_at),
        **metrics,
    }


@router.get("/stats")
async def referral_stats(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Estadísticas globales del módulo de referidos."""
    codes = (await db.scalars(select(ReferralCode))).all()
    total_referrals = 0
    total_worked = 0
    for c in codes:
        m = await referral_service.get_referrer_metrics(db, c.operator_id)
        total_referrals += m["total_referrals"]
        total_worked += m["worked_referrals"]
    return {
        "total_codes": len(codes),
        "active_codes": sum(1 for c in codes if c.is_active),
        "total_referrals": total_referrals,
        "total_worked": total_worked,
    }


@router.get("/codes")
async def list_codes(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos los códigos con métricas de su referente."""
    codes = (await db.scalars(
        select(ReferralCode).order_by(ReferralCode.created_at.desc())
    )).all()
    return [await _code_with_metrics(db, c) for c in codes]


@router.post("/codes", status_code=201)
async def create_code(
    body: dict,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Genera un código de referido para un operador (SuperAdmin only)."""
    operator_id = body.get("operator_id")
    if not operator_id:
        raise HTTPException(status_code=400, detail="operator_id es requerido")
    try:
        op_uuid = uuid.UUID(str(operator_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="operator_id inválido")

    operator = await _resolve_operator(db, op_uuid)
    try:
        code = await referral_service.create_code_for_operator(db, operator.id, current_user.id)
    except ReferralError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return await _code_with_metrics(db, code)


@router.patch("/codes/{code_id}")
async def toggle_code(
    code_id: uuid.UUID,
    body: dict,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Habilita/deshabilita un código de referido."""
    if "is_active" not in body or not isinstance(body["is_active"], bool):
        raise HTTPException(status_code=400, detail="is_active (bool) es requerido")
    try:
        code = await referral_service.set_code_active(db, code_id, body["is_active"], current_user.id)
    except ReferralError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return await _code_with_metrics(db, code)


@router.get("/export")
async def export_referrals(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Exporta los referidos a Excel (.xlsx)."""
    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(status_code=501, detail="openpyxl no instalado")

    wb = Workbook()
    ws = wb.active
    ws.title = "Referidos"
    ws.append([
        "Referente", "Documento Referente", "Código", "Código Activo",
        "Referido", "Documento Referido", "Fecha Registro", "Referido Activo",
    ])

    referrals = (await db.scalars(
        select(Referral).order_by(Referral.registered_at.desc())
    )).all()
    for ref in referrals:
        referrer_op = await db.get(Operator, ref.referrer_operator_id)
        referrer_user = await db.get(User, referrer_op.user_id) if referrer_op and referrer_op.user_id else None
        referred_op = await db.get(Operator, ref.referred_operator_id)
        referred_user = await db.get(User, referred_op.user_id) if referred_op and referred_op.user_id else None
        ws.append([
            _operator_label(referrer_user),
            referrer_user.document_number if referrer_user else "",
            ref.code_used,
            "Sí" if referrer_op else "No",
            _operator_label(referred_user),
            referred_user.document_number if referred_user else "",
            str(ref.registered_at or ""),
            "Sí" if referred_op and referred_op.is_active else "No",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"referidos_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/public/codes")
async def public_active_codes(db: AsyncSession = Depends(get_db)):
    """Códigos de referido ACTIVOS (público, sin auth).

    Alimenta el desplegable del formulario de registro: [{code, name}].
    """
    rows = (
        await db.execute(
            select(ReferralCode, Operator, User)
            .join(Operator, ReferralCode.operator_id == Operator.id)
            .outerjoin(User, Operator.user_id == User.id)
            .where(ReferralCode.is_active == True, Operator.is_active == True)
            .order_by(User.first_name, User.last_name)
        )
    ).all()
    return {
        "items": [
            {
                "code": code.code,
                "name": f"{user.first_name} {user.last_name}".strip() if user else "",
            }
            for code, op, user in rows
        ]
    }


@router.get("/{operator_id}")
async def referrer_detail(
    operator_id: uuid.UUID,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Detalle de un referente: métricas + lista de referidos."""
    operator = await _resolve_operator(db, operator_id)

    metrics = await referral_service.get_referrer_metrics(db, operator.id)
    referrals = []
    for ref in await referral_service.list_referrals_of(db, operator.id):
        referred_op = await db.get(Operator, ref.referred_operator_id)
        referred_user = await db.get(User, referred_op.user_id) if referred_op and referred_op.user_id else None
        referrals.append({
            "id": str(ref.id),
            "name": _operator_label(referred_user),
            "document": referred_user.document_number if referred_user else None,
            "is_active": bool(referred_op and referred_op.is_active),
            "registered_at": str(ref.registered_at or ""),
            "code_used": ref.code_used,
        })

    code = await db.scalar(
        select(ReferralCode).where(ReferralCode.operator_id == operator.id)
    )
    user = await db.get(User, operator.user_id) if operator.user_id else None
    return {
        "operator_id": str(operator.id),
        "operator_user_id": str(operator.user_id) if operator.user_id else None,
        "operator_name": _operator_label(user),
        "code": {
            "id": str(code.id), "code": code.code, "is_active": code.is_active,
        } if code else None,
        "metrics": metrics,
        "referrals": referrals,
    }


# --- Página SuperAdmin (SSR) ---
page_router = APIRouter(tags=["Referrals"])


@page_router.get("/admin/referrals", include_in_schema=False)
async def referrals_page(request: Request):
    """Página de gestión de referidos (SuperAdmin)."""
    return templates.TemplateResponse("admin/referrals.html", {"request": request})