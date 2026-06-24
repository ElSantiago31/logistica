
import os
import uuid
from typing import Optional, Tuple, List
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile, HTTPException, status
from PIL import Image

from app.models.users import User
from app.models.operators import Operator
from app.models.blocked_document import BlockedDocument
from app.schemas.operators import OperatorUpdateRequest, OperatorAdminUpdateRequest
from app.config import settings
from app.services.photos import delete_operator_photos

def _ensure_photo_dirs():
    """Ensure that the directories for photos exist."""
    os.makedirs(settings.PHOTOS_DIR, exist_ok=True)
    os.makedirs(settings.PHOTOS_THUMBNAIL_DIR, exist_ok=True)

# Education level hierarchy for smart matching
EDU_ORDER = {"primaria": 1, "secundaria": 2, "tecnico": 3, "tecnologo": 4, "universitario": 5, "postgrado": 6}

import unicodedata

def _normalize_city(name: str) -> str:
    """Remove accents and normalize city name for matching."""
    if not name:
        return ""
    nfkd = unicodedata.normalize('NFKD', name)
    stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
    for suffix in [', D.C.', ', D.C', ', D.C.,', ' D.C.', ' D.C']:
        stripped = stripped.replace(suffix, '')
    return stripped.strip().lower()


async def get_operators(
    db: AsyncSession, 
    skip: int = 0, 
    limit: int = 100, 
    is_approved: Optional[bool] = None,
    is_active: bool = True,
    search: Optional[str] = None,
    experience_role_id: Optional[str] = None,
    city: Optional[str] = None,
    education_level: Optional[str] = None,
    exclude_event_id: Optional[str] = None,
) -> Tuple[List[User], int]:
    """Get a list of operators with basic filtering and pagination.
    city: filter by operator city (accent-insensitive partial match).
    education_level: filter operators with education >= this level.
    exclude_event_id: exclude operators already assigned to this event.
    """
    from sqlalchemy.orm import joinedload
    from sqlalchemy import or_, func as sa_func

    # Base query for selecting
    query = select(User).where(
        User.user_type == "operator",
        User.is_active == is_active
    ).options(
        selectinload(User.operator_profile).joinedload(Operator.eps),
        selectinload(User.operator_profile).joinedload(Operator.arl),
    )

    # Base count
    count_query = select(func.count()).select_from(User).where(
        User.user_type == "operator",
        User.is_active == is_active
    )

    if is_approved is not None:
        count_query = count_query.where(User.is_approved == is_approved)
        query = query.where(User.is_approved == is_approved)

    # Exclude already assigned to event
    if exclude_event_id:
        from app.models.events import EventAssignment
        assigned_sq = select(Operator.user_id).join(
            EventAssignment, EventAssignment.operator_id == Operator.id
        ).where(
            EventAssignment.event_id == exclude_event_id
        )
        query = query.where(User.id.notin_(assigned_sq))
        count_query = count_query.where(User.id.notin_(assigned_sq))

    # Search by name, email, or document
    if search:
        pattern = f"%{search}%"
        search_filter = or_(
            User.first_name.ilike(pattern),
            User.last_name.ilike(pattern),
            User.email.ilike(pattern),
            User.document_number.ilike(pattern),
            User.phone.ilike(pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # Filter by experience role (JSON field contains role ID)
    need_operator_join = experience_role_id or city or education_level
    if need_operator_join:
        query = query.join(Operator, Operator.user_id == User.id)
        count_query = count_query.join(Operator, Operator.user_id == User.id)

        if experience_role_id:
            exp_filter = Operator.experience_roles.contains(experience_role_id)
            query = query.where(exp_filter)
            count_query = count_query.where(exp_filter)

        # Filter by city (accent-insensitive, case-insensitive match)
        # PostgreSQL ILIKE is already case-insensitive for ASCII; we normalize
        # accents on the DB side via a single unaccent-like expression, but we
        # ALSO normalize on Python side. To keep it portable (no extension
        # dependency) we use a simpler approach: remove the most common suffixes
        # from the search term and do a case-insensitive contains match.
        if city:
            normalized = _normalize_city(city)  # sin acentos, sin ", D.C.", lower
            # Build accent-insensitive pattern using regex (PostgreSQL ~* operator)
            # This converts "bogota" into a pattern that matches "Bogotá" or "BOGOTÁ"
            accent_map = {'a': '[aá]', 'e': '[eé]', 'i': '[ií]', 'o': '[oó]', 'u': '[uú]', 'n': '[nñ]'}
            regex_pattern = ''.join(accent_map.get(ch, ch) for ch in normalized)
            # Use PostgreSQL regex case-insensitive operator (~*)
            city_filter = Operator.city.op('~*')(f"{regex_pattern}")
            query = query.where(city_filter)
            count_query = count_query.where(city_filter)

        # Filter by education level (operators with level >= required)
        if education_level:
            min_val = EDU_ORDER.get(education_level, 0)
            valid_levels = [k for k, v in EDU_ORDER.items() if v >= min_val]
            edu_filter = Operator.education_level.in_(valid_levels)
            query = query.where(edu_filter)
            count_query = count_query.where(edu_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    operators = result.scalars().all()

    return list(operators), total

async def get_operator(db: AsyncSession, user_id: uuid.UUID, include_inactive: bool = False) -> Optional[User]:
    """Get a specific operator by user ID."""
    from sqlalchemy.orm import joinedload
    query = select(User).where(
        User.id == user_id,
        User.user_type == "operator",
    )
    if not include_inactive:
        query = query.where(User.is_active == True)
    query = query.options(
        selectinload(User.operator_profile).joinedload(Operator.eps),
        selectinload(User.operator_profile).joinedload(Operator.arl),
    )
    
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def update_operator(
    db: AsyncSession, 
    user_id: uuid.UUID, 
    update_data: OperatorUpdateRequest | OperatorAdminUpdateRequest,
    is_admin: bool = False
) -> Optional[User]:
    """Update operator profile data."""
    user = await get_operator(db, user_id, include_inactive=is_admin)
    if not user:
        return None

    update_dict = update_data.model_dump(exclude_unset=True)
    
    # Fields belonging to User model
    user_fields = ["first_name", "last_name", "phone"]
    # Admin only fields for User
    admin_user_fields = ["is_verified", "is_approved", "role_id", "is_active", "document_number", "document_type", "email"]
    
    if is_admin:
        user_fields.extend(admin_user_fields)
        
    for field in user_fields:
        if field in update_dict:
            val = update_dict[field]
            # Validate document_number uniqueness if changing
            if field == "document_number" and val and val != user.document_number:
                existing = await db.execute(
                    select(User).where(User.document_number == val, User.id != user.id, User.is_active == True)
                )
                if existing.scalar_one_or_none():
                    raise HTTPException(status_code=409, detail="El número de documento ya está en uso por otro usuario")
                # Check blocked documents
                blocked = await db.execute(
                    select(BlockedDocument).where(
                        BlockedDocument.document_number == val,
                        BlockedDocument.is_active == True,
                    )
                )
                if blocked.scalar_one_or_none():
                    raise HTTPException(status_code=403, detail="Este documento está bloqueado")
            setattr(user, field, val)
            
    # Fields belonging to Operator model
    if hasattr(user, "operator_profile") and user.operator_profile:
        operator_fields = [
            "city", "address", "locality", "blood_type", "emergency_contact_name", 
            "emergency_contact_phone", "eps_id", "arl_id", "birth_date", "gender",
            "whatsapp", "has_protocol_experience", "event_size_experience",
            "shirt_size", "jacket_size"
        ]
        admin_operator_fields = ["background_check_status", "notes", "education_level"]
        
        if is_admin:
            operator_fields.extend(admin_operator_fields)
            
        for field in operator_fields:
            if field in update_dict:
                setattr(user.operator_profile, field, update_dict[field])

        # experience_roles: lista de role_ids -> JSON string
        if is_admin and "experience_roles" in update_dict:
            import json
            roles_list = update_dict["experience_roles"]
            if roles_list:
                user.operator_profile.experience_roles = json.dumps(
                    [str(r) for r in roles_list]
                )
            else:
                user.operator_profile.experience_roles = None

    await db.commit()
    await db.refresh(user)
    return user

async def delete_operator(db: AsyncSession, user_id: uuid.UUID, hard_delete: bool = True) -> bool:
    """Delete an operator.

    Hard delete (default): permanently removes ALL operator data to comply with
    data protection laws (Ley de Tratamiento de Datos) and free disk space.
    The operator will NOT appear in any list (active or inactive/blocked).

    Soft delete (hard_delete=False): legacy behavior, just marks as inactive.

    Order of deletion (child → parent) to respect FK constraints:
    1. Photos (disk files)
    2. Signatures (via Payroll or directly)
    3. Payrolls
    4. Evaluations
    5. Event assignments
    6. Blocked documents pointing to this user (clear operator_user_id)
    7. Revoked tokens
    8. Audit logs (user_id is not FK, set to NULL)
    9. Operator profile
    10. User
    """
    user = await get_operator(db, user_id, include_inactive=True)
    if not user:
        return False

    if hard_delete:
        from sqlalchemy import delete as sql_delete
        # Find operator profile (needed for photo cleanup + cascade deletes)
        op_result = await db.execute(
            select(Operator).where(Operator.user_id == user_id)
        )
        operator = op_result.scalar_one_or_none()

        # 1. Delete photo files from disk
        if operator and operator.photo_path:
            delete_operator_photos(
                operator.photo_path,
                operator.photo_thumbnail_path,
            )

        if operator:
            # 2-5. Delete all child records that reference this operator
            from app.models.payroll import PayrollRecord, Evaluation
            from app.models.events import EventAssignment

            # Payroll records (includes signature_data + invoice)
            await db.execute(
                sql_delete(PayrollRecord).where(PayrollRecord.operator_id == operator.id)
            )
            # Evaluations
            await db.execute(
                sql_delete(Evaluation).where(Evaluation.operator_id == operator.id)
            )
            # Event assignments
            await db.execute(
                sql_delete(EventAssignment).where(EventAssignment.operator_id == operator.id)
            )

        # 6. Clear blocked documents pointing to this user (SET NULL equivalent)
        await db.execute(
            sql_delete(BlockedDocument).where(BlockedDocument.operator_user_id == user_id)
        )

        # 7. Delete revoked tokens
        from app.models.audit import RevokedToken
        await db.execute(
            sql_delete(RevokedToken).where(RevokedToken.user_id == user_id)
        )

        # 8. Nullify audit logs (user_id is not FK but should be cleared)
        from app.models.audit import AuditLog
        await db.execute(
            sql_delete(AuditLog).where(AuditLog.user_id == user_id)
        )

        # 9. Delete operator profile
        if operator:
            await db.execute(
                sql_delete(Operator).where(Operator.id == operator.id)
            )

        # 10. Finally, hard delete the user
        await db.execute(
            sql_delete(User).where(User.id == user_id)
        )

        await db.commit()
        return True

    # --- Legacy soft delete (kept for compatibility, not used by UI) ---
    if user.operator_profile and user.operator_profile.photo_path:
        delete_operator_photos(
            user.operator_profile.photo_path,
            user.operator_profile.photo_thumbnail_path,
        )
        user.operator_profile.photo_path = None
        user.operator_profile.photo_thumbnail_path = None

    user.is_active = False
    user.document_number = None
    suffix = f"_deleted_{user_id.hex[:8]}"
    if user.email:
        user.email = f"{user.email}{suffix}"
    await db.commit()
    return True

async def block_operator(
    db: AsyncSession, 
    user_id: uuid.UUID, 
    blocked_by: uuid.UUID,
    reason: Optional[str] = None,
) -> bool:
    """Block an operator: add document to blocked list and deactivate."""
    user = await get_operator(db, user_id, include_inactive=True)
    if not user:
        return False

    # Create blocked document entry
    if user.document_number:
        blocked_doc = BlockedDocument(
            document_type=user.document_type,
            document_number=user.document_number,
            reason=reason,
            blocked_by=blocked_by,
            operator_user_id=user.id,
            operator_name=f"{user.first_name} {user.last_name}",
        )
        db.add(blocked_doc)

    # Delete photo files from disk + clear DB references
    if user.operator_profile and user.operator_profile.photo_path:
        delete_operator_photos(
            user.operator_profile.photo_path,
            user.operator_profile.photo_thumbnail_path,
        )
        user.operator_profile.photo_path = None
        user.operator_profile.photo_thumbnail_path = None

    # Soft-delete the user
    user.is_active = False
    user.document_number = None
    suffix = f"_blocked_{user_id.hex[:8]}"
    if user.email:
        user.email = f"{user.email}{suffix}"
    await db.commit()
    return True


async def unblock_operator(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Unblock an operator: reactivate user (document number was freed on block)."""
    user = await get_operator(db, user_id, include_inactive=True)
    if not user:
        return False

    # Remove active blocks for this operator's original documents
    blocks = await db.execute(
        select(BlockedDocument).where(
            BlockedDocument.operator_user_id == user_id,
            BlockedDocument.is_active == True,
        )
    )
    for block in blocks.scalars().all():
        block.is_active = False

    # Reactivate user
    user.is_active = True
    # Restore email by removing the _blocked_ suffix
    if user.email and "_blocked_" in user.email:
        user.email = user.email.split("_blocked_")[0]
    await db.commit()
    return True


async def search_blocked_documents(
    db: AsyncSession, 
    search: Optional[str] = None,
) -> list:
    """Search blocked documents."""
    query = select(BlockedDocument).where(BlockedDocument.is_active == True)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            BlockedDocument.document_number.ilike(pattern) |
            BlockedDocument.operator_name.ilike(pattern)
        )
    query = query.order_by(BlockedDocument.created_at.desc())
    result = await db.execute(query)
    blocks = result.scalars().all()
    return [
        {
            "id": str(b.id),
            "document_type": b.document_type,
            "document_number": b.document_number,
            "reason": b.reason,
            "operator_name": b.operator_name,
            "operator_user_id": str(b.operator_user_id) if b.operator_user_id else None,
            "created_at": str(b.created_at),
        }
        for b in blocks
    ]


async def upload_operator_photo(db: AsyncSession, user_id: uuid.UUID, file: UploadFile) -> Optional[User]:
    """Upload and process operator photo."""
    user = await get_operator(db, user_id)
    if not user or not user.operator_profile:
        return None

    _ensure_photo_dirs()

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large. Max size is 5MB.")

    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file type. Only JPEG, PNG, WEBP are allowed.")

    file_ext = file.filename.split(".")[-1]
    filename = f"{user_id}_{uuid.uuid4().hex[:8]}.{file_ext}"
    
    photo_path = os.path.join(settings.PHOTOS_DIR, filename)
    thumbnail_path = os.path.join(settings.PHOTOS_THUMBNAIL_DIR, filename)

    try:
        with open(photo_path, "wb") as buffer:
            buffer.write(await file.read())

        with Image.open(photo_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.thumbnail((300, 300))
            img.save(thumbnail_path, format="JPEG", quality=85)
            
        user.operator_profile.photo_path = f"/static/photos/{filename}"
        user.operator_profile.photo_thumbnail_path = f"/static/photos/thumbnails/{filename}"
        
        await db.commit()
        await db.refresh(user)
        return user
        
    except Exception as e:
        if os.path.exists(photo_path):
            os.remove(photo_path)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process image: {str(e)}")