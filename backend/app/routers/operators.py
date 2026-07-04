import io
import json
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.users import User
from app.models.operators import Operator
from app.models.roles import Role
from app.schemas.operators import OperatorResponse, OperatorListResponse, OperatorAdminUpdateRequest
from app.services.operators import (
    get_operators, get_operator, update_operator, delete_operator, 
    upload_operator_photo, block_operator, unblock_operator, search_blocked_documents
)
from app.services.photos import save_operator_photo_bytes, delete_operator_photos
from app.dependencies.auth import get_current_active_user, require_admin_or_coordinator, require_superadmin

router = APIRouter(prefix="/api/operators", tags=["Operators"])


# --- Dashboard Stats ---

@router.get("/dashboard/stats")
async def dashboard_stats(
    current_user: User = Depends(require_admin_or_coordinator),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard statistics: active events, total operators, operators grouped by role."""
    from app.models.events import Event
    from app.models.roles import Role
    from sqlalchemy import func
    import json as json_mod

    active_events_result = await db.execute(
        select(func.count()).select_from(Event).where(
            Event.status.in_(["published", "in_progress"])
        )
    )
    active_events = active_events_result.scalar() or 0

    total_ops_result = await db.execute(
        select(func.count()).select_from(Operator).join(User, Operator.user_id == User.id).where(User.is_active == True)
    )
    total_operators = total_ops_result.scalar() or 0

    roles_result = await db.execute(select(Role).order_by(Role.name))
    roles = roles_result.scalars().all()

    ops_result = await db.execute(
        select(Operator, User).join(User, Operator.user_id == User.id).where(User.is_active == True)
    )
    all_operators = ops_result.all()

    sin_experiencia = []
    for op, user in all_operators:
        has_role = False
        if op.experience_roles:
            try:
                exp_roles = json_mod.loads(op.experience_roles)
                if exp_roles:
                    has_role = True
            except (json_mod.JSONDecodeError, TypeError):
                pass
        if not has_role:
            sin_experiencia.append({
                "id": str(user.id),
                "name": f"{user.first_name} {user.last_name}",
                "phone": user.phone or "",
                "city": op.city or "",
                "photo_thumbnail_path": op.photo_thumbnail_path or None,
            })

    operators_by_role = []
    for role in roles:
        members = []
        for op, user in all_operators:
            if op.experience_roles:
                try:
                    exp_roles = json_mod.loads(op.experience_roles)
                    if str(role.id) in exp_roles:
                        members.append({
                            "id": str(user.id),
                            "name": f"{user.first_name} {user.last_name}",
                            "phone": user.phone or "",
                            "city": op.city or "",
                            "photo_thumbnail_path": op.photo_thumbnail_path or None,
                        })
                except (json_mod.JSONDecodeError, TypeError):
                    pass
        operators_by_role.append({
            "role_id": str(role.id),
            "role_name": role.name,
            "role_slug": role.slug,
            "count": len(members),
            "members": members,
        })

    return {
        "active_events": active_events,
        "total_operators": total_operators,
        "operators_by_role": operators_by_role,
        "sin_experiencia": sin_experiencia,
    }


# --- Operator Self-Service Profile (MUST be before /{user_id}) ---

@router.get("/me/profile")
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current operator's own profile."""
    result = await db.execute(
        select(Operator).where(Operator.user_id == current_user.id)
    )
    operator = result.scalar_one_or_none()
    return {
        "email": current_user.email,
        "user": {
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "document_type": current_user.document_type,
            "document_number": current_user.document_number,
            "phone": current_user.phone,
        },
        "operator": {
            "eps_id": str(operator.eps_id) if operator and operator.eps_id else None,
            "pension_fund_id": str(operator.pension_fund_id) if operator and operator.pension_fund_id else None,
            "city": operator.city if operator else None,
            "address": operator.address if operator else None,
            "locality": operator.locality if operator else None,
            "whatsapp": operator.whatsapp if operator else None,
            "blood_type": operator.blood_type if operator else None,
            "emergency_contact_name": operator.emergency_contact_name if operator else None,
            "emergency_contact_phone": operator.emergency_contact_phone if operator else None,
            "has_protocol_experience": operator.has_protocol_experience if operator else None,
            "event_size_experience": operator.event_size_experience if operator else None,
            "shirt_size": operator.shirt_size if operator else None,
            "jacket_size": operator.jacket_size if operator else None,
            "experience_roles": operator.experience_roles if operator else None,
            "photo_path": operator.photo_path if operator else None,
            "photo_thumbnail_path": operator.photo_thumbnail_path if operator else None,
        } if operator else {},
    }


@router.put("/me/profile")
async def update_my_profile(
    update_data: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current operator's own profile."""
    if "phone" in update_data and update_data["phone"]:
        current_user.phone = update_data["phone"]

    result = await db.execute(
        select(Operator).where(Operator.user_id == current_user.id)
    )
    operator = result.scalar_one_or_none()
    if not operator:
        operator = Operator(user_id=current_user.id)
        db.add(operator)
        await db.flush()

    field_map = [
        "eps_id", "pension_fund_id", "city", "address", "locality", "whatsapp",
        "blood_type", "emergency_contact_name", "emergency_contact_phone",
        "has_protocol_experience", "event_size_experience",
        "shirt_size", "jacket_size",
    ]
    for field in field_map:
        if field in update_data and update_data[field] is not None:
            val = update_data[field]
            if field in ("eps_id", "pension_fund_id") and val:
                val = uuid.UUID(val)
            if field == "has_protocol_experience":
                val = val == "true" if isinstance(val, str) else bool(val)
            setattr(operator, field, val)

    if "experience_roles" in update_data and update_data["experience_roles"]:
        roles = update_data["experience_roles"]
        # Security: filtrar roles event-only (no permitidos en perfil de operador).
        valid_roles = await db.execute(
            select(Role.id).where(
                Role.id.in_([uuid.UUID(str(r)) for r in roles]),
                Role.is_event_only == False,
                Role.is_active == True,
            )
        )
        valid_ids = [str(r) for r in valid_roles.scalars().all()]
        if len(valid_ids) != len(roles):
            raise HTTPException(
                status_code=400,
                detail="Uno o más roles seleccionados no son válidos",
            )
        operator.experience_roles = json.dumps(valid_ids)

    await db.commit()
    return {"message": "Perfil actualizado correctamente"}


# --- Admin endpoints ---

@router.get("/blocked/search")
async def search_blocked(
    search: Optional[str] = Query(None, min_length=1),
    current_user: User = Depends(require_admin_or_coordinator),
    db: AsyncSession = Depends(get_db),
):
    """Search blocked documents."""
    results = await search_blocked_documents(db, search=search)
    return {"items": results, "total": len(results)}


@router.get("/search")
async def search_operators_for_staff(
    q: str = Query(..., min_length=2, description="Buscar por nombre o cédula"),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(require_admin_or_coordinator),
    db: AsyncSession = Depends(get_db),
):
    """Busca operadores por nombre o cédula.

    Pensado para el buscador de la sección 'Personal del Sistema' al crear/editar
    eventos: permite asignar operadores como checkin/intendencia de un evento.
    Devuelve {user_id, full_name, document_number, photo}.
    """
    from sqlalchemy import or_, func as sql_func

    term = f"%{q.strip().lower()}%"
    result = await db.execute(
        select(User, Operator)
        .outerjoin(Operator, Operator.user_id == User.id)
        .where(
            User.user_type == "operator",
            User.is_active == True,
            or_(
                sql_func.lower(User.first_name).like(term),
                sql_func.lower(User.last_name).like(term),
                User.document_number.ilike(term),
            ),
        )
        .limit(limit)
    )
    rows = result.all()
    return {
        "items": [
            {
                "user_id": str(u.id),
                "full_name": f"{u.first_name} {u.last_name}",
                "document_number": u.document_number,
                "photo": op.photo_thumbnail_path if op else None,
            }
            for u, op in rows
        ],
        "total": len(rows),
    }


@router.get("/coordinators")
async def list_coordinators(
    current_user: User = Depends(require_admin_or_coordinator),
    db: AsyncSession = Depends(get_db),
):
    """Lista coordinadores y operadores aptos para recibir cupos de coordinación.

    Devuelve campos normalizados para el selector de cupos en crear/editar evento:
    operator_id, user_id, full_name, document_number, phone, user_type.

    Incluye cualquier usuario con perfil de operador (coordinator u operator),
    ya que los cupos (EventCoordinatorQuota) referencian operators.id.
    Prioriza coordinadores primero, luego operadores, ordenados alfabéticamente.
    """
    result = await db.execute(
        select(Operator, User)
        .join(User, User.id == Operator.user_id)
        .where(User.is_active == True)
        .order_by(User.first_name, User.last_name)
    )
    rows = result.all()
    # Ordenar: coordinadores primero, luego operadores
    rows.sort(key=lambda r: (0 if r[1].user_type == "coordinator" else 1, r[1].first_name))
    return {
        "items": [
            {
                "operator_id": str(op.id),
                "user_id": str(u.id),
                "full_name": f"{u.first_name} {u.last_name}",
                "document_number": u.document_number,
                "phone": u.phone,
                "user_type": u.user_type,
            }
            for op, u in rows
        ],
        "total": len(rows),
    }


@router.get("/", response_model=OperatorListResponse)
async def list_operators(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_approved: Optional[bool] = Query(None),
    is_active: bool = Query(True),
    search: Optional[str] = Query(None, min_length=1),
    experience_role_id: Optional[str] = Query(None),
    role_level: Optional[str] = Query(None, description="Filtrar por nivel(es) jerárquicos de rol (csv, e.g. '1,2')"),
    city: Optional[str] = Query(None, description="Filtrar por ciudad del operador"),
    education_level: Optional[str] = Query(None, description="Filtrar por nivel educativo minimo"),
    exclude_event_id: Optional[str] = Query(None, description="Excluir operadores ya asignados a este evento"),
    current_user: User = Depends(require_admin_or_coordinator),
    db: AsyncSession = Depends(get_db)
):
    """List all operators. Supports search, city filter, education level filter, and role filter."""
    operators, total = await get_operators(
        db, skip, limit, is_approved, is_active,
        search=search, experience_role_id=experience_role_id,
        role_level=role_level,
        city=city, education_level=education_level,
        exclude_event_id=exclude_event_id,
    )
    return OperatorListResponse(items=operators, total=total)

@router.get("/{user_id}/block-info")
async def get_block_info(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin_or_coordinator),
    db: AsyncSession = Depends(get_db),
):
    """Get block information for a specific operator."""
    from app.models.blocked_document import BlockedDocument
    blocks = await db.execute(
        select(BlockedDocument).where(
            BlockedDocument.operator_user_id == user_id,
            BlockedDocument.is_active == True,
        ).order_by(BlockedDocument.created_at.desc())
    )
    active_blocks = blocks.scalars().all()
    if not active_blocks:
        return {"blocked": False, "blocks": []}
    return {
        "blocked": True,
        "blocks": [
            {
                "id": str(b.id),
                "document_type": b.document_type,
                "document_number": b.document_number,
                "reason": b.reason,
                "blocked_by": str(b.blocked_by) if b.blocked_by else None,
                "created_at": str(b.created_at),
            }
            for b in active_blocks
        ],
    }


@router.get("/{user_id}", response_model=OperatorResponse)
async def get_operator_details(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific operator."""
    is_admin = current_user.user_type in ["superadmin", "coordinator"]
    if not is_admin and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        
    # Admins can see inactive (blocked) operators
    operator = await get_operator(db, user_id, include_inactive=is_admin)
    if not operator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")
        
    return operator

@router.put("/{user_id}", response_model=OperatorResponse)
async def update_operator_profile(
    user_id: uuid.UUID,
    update_data: OperatorAdminUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update operator profile. Admins can update more fields than the operator themselves."""
    is_admin = current_user.user_type in ["superadmin", "coordinator"]
    if not is_admin and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    # Admins can update inactive (blocked) operators
    operator = await get_operator(db, user_id, include_inactive=is_admin)
    if not operator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")

    updated_operator = await update_operator(db, user_id, update_data, is_admin=is_admin)
    return updated_operator

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_operator(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin_or_coordinator),
    db: AsyncSession = Depends(get_db)
):
    """Soft delete an operator. Requires admin/coordinator role."""
    success = await delete_operator(db, user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")

@router.post("/{user_id}/photo", response_model=OperatorResponse)
async def upload_photo(
    user_id: uuid.UUID,
    photo: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a profile photo for the operator (authenticated)."""
    import os
    from app.config import settings

    if current_user.user_type not in ["superadmin", "coordinator"] and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    # Get operator profile directly
    op_result = await db.execute(select(Operator).where(Operator.user_id == user_id))
    operator = op_result.scalar_one_or_none()
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")

    # Validate
    photo.file.seek(0, 2)
    file_size = photo.file.tell()
    photo.file.seek(0)
    if file_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Archivo muy grande. Max 5MB.")
    if photo.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=400, detail="Tipo invalido. Solo JPEG, PNG, WEBP.")

    try:
        contents = await photo.read()
        # Delete old photo files first (if any)
        delete_operator_photos(operator.photo_path, operator.photo_thumbnail_path)
        # Use centralized service — compresses + generates thumbnail
        photo_url, thumb_url = save_operator_photo_bytes(contents, user_id)
        operator.photo_path = photo_url
        operator.photo_thumbnail_path = thumb_url
        await db.commit()
        # Return fresh operator data
        operator = await get_operator(db, user_id)
        return operator
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando imagen: {str(e)}")


@router.delete("/{user_id}/photo", status_code=status.HTTP_200_OK)
async def delete_operator_photo(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin_or_coordinator),
    db: AsyncSession = Depends(get_db),
):
    """Delete an operator's profile photo (admin/coordinator only).

    Removes the photo + thumbnail files from disk and clears the DB fields.
    Useful when an operator uploads an incorrect or inappropriate photo.
    """
    op_result = await db.execute(select(Operator).where(Operator.user_id == user_id))
    operator = op_result.scalar_one_or_none()
    if not operator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operador no encontrado")

    if not operator.photo_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El operador no tiene foto asignada",
        )

    # Delete files from disk (safe if already missing)
    delete_operator_photos(operator.photo_path, operator.photo_thumbnail_path)

    # Clear DB fields
    operator.photo_path = None
    operator.photo_thumbnail_path = None
    await db.commit()

    return {"message": "Foto eliminada correctamente"}


@router.post("/{user_id}/block")
async def block_operator_endpoint(
    user_id: uuid.UUID,
    request: dict,
    current_user: User = Depends(require_admin_or_coordinator),
    db: AsyncSession = Depends(get_db),
):
    """Block an operator — adds their document to the blocked list and deactivates them."""
    reason = request.get("reason", "Bloqueado por administrador")
    success = await block_operator(db, user_id, current_user.id, reason=reason)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operador no encontrado")
    return {"message": "Operador bloqueado exitosamente"}


@router.post("/{user_id}/unblock")
async def unblock_operator_endpoint(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin_or_coordinator),
    db: AsyncSession = Depends(get_db),
):
    """Unblock a previously blocked operator — reactivates their account."""
    success = await unblock_operator(db, user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operador no encontrado")
    return {"message": "Operador desbloqueado exitosamente"}
