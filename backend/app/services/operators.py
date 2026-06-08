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
from app.schemas.operators import OperatorUpdateRequest, OperatorAdminUpdateRequest
from app.config import settings

def _ensure_photo_dirs():
    """Ensure that the directories for photos exist."""
    os.makedirs(settings.PHOTOS_DIR, exist_ok=True)
    os.makedirs(settings.PHOTOS_THUMBNAIL_DIR, exist_ok=True)

async def get_operators(
    db: AsyncSession, 
    skip: int = 0, 
    limit: int = 100, 
    is_approved: Optional[bool] = None,
    is_active: bool = True,
    search: Optional[str] = None,
    experience_role_id: Optional[str] = None,
) -> Tuple[List[User], int]:
    """Get a list of operators with basic filtering and pagination."""
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
    if experience_role_id:
        exp_filter = Operator.experience_roles.contains(experience_role_id)
        query = query.join(Operator, Operator.user_id == User.id).where(exp_filter)
        count_query = count_query.join(Operator, Operator.user_id == User.id).where(exp_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    operators = result.scalars().all()

    return list(operators), total

async def get_operator(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Get a specific operator by user ID."""
    from sqlalchemy.orm import joinedload
    query = select(User).where(
        User.id == user_id,
        User.user_type == "operator"
    ).options(
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
    user = await get_operator(db, user_id)
    if not user:
        return None

    update_dict = update_data.model_dump(exclude_unset=True)
    
    # Fields belonging to User model
    user_fields = ["first_name", "last_name", "phone"]
    # Admin only fields for User
    admin_user_fields = ["is_verified", "is_approved", "role_id", "is_active"]
    
    if is_admin:
        user_fields.extend(admin_user_fields)
        
    for field in user_fields:
        if field in update_dict:
            setattr(user, field, update_dict[field])
            
    # Fields belonging to Operator model
    if hasattr(user, "operator_profile") and user.operator_profile:
        operator_fields = [
            "city", "address", "locality", "blood_type", "emergency_contact_name", 
            "emergency_contact_phone", "eps_id", "arl_id", "birth_date",
            "whatsapp", "has_protocol_experience", "event_size_experience",
            "shoe_size", "shirt_size", "pants_size", "jacket_size"
        ]
        admin_operator_fields = ["background_check_status", "notes"]
        
        if is_admin:
            operator_fields.extend(admin_operator_fields)
            
        for field in operator_fields:
            if field in update_dict:
                setattr(user.operator_profile, field, update_dict[field])

    await db.commit()
    await db.refresh(user)
    return user

async def delete_operator(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Soft delete an operator. Frees document_number and email for re-registration."""
    user = await get_operator(db, user_id)
    if not user:
        return False

    user.is_active = False
    # Free up unique fields so they can be reused on re-registration
    # NULL is safe because PostgreSQL allows multiple NULLs in UNIQUE columns
    user.document_number = None
    suffix = f"_deleted_{user_id.hex[:8]}"
    if user.email:
        user.email = f"{user.email}{suffix}"
    await db.commit()
    return True

async def upload_operator_photo(db: AsyncSession, user_id: uuid.UUID, file: UploadFile) -> Optional[User]:
    """Upload and process operator photo."""
    user = await get_operator(db, user_id)
    if not user or not user.operator_profile:
        return None

    _ensure_photo_dirs()

    # Validate file size (e.g., 5MB)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    # max size 5MB
    if file_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large. Max size is 5MB.")

    # Validate content type
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file type. Only JPEG, PNG, WEBP are allowed.")

    file_ext = file.filename.split(".")[-1]
    filename = f"{user_id}_{uuid.uuid4().hex[:8]}.{file_ext}"
    
    photo_path = os.path.join(settings.PHOTOS_DIR, filename)
    thumbnail_path = os.path.join(settings.PHOTOS_THUMBNAIL_DIR, filename)

    try:
        # Save original photo
        with open(photo_path, "wb") as buffer:
            buffer.write(await file.read())

        # Generate thumbnail
        with Image.open(photo_path) as img:
            # Convert to RGB if needed (e.g. RGBA png)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.thumbnail((300, 300))
            img.save(thumbnail_path, format="JPEG", quality=85)
            
        # Update db
        # Return relative paths for the API to serve them via static files
        user.operator_profile.photo_path = f"/static/photos/{filename}"
        user.operator_profile.photo_thumbnail_path = f"/static/photos/thumbnails/{filename}"
        
        await db.commit()
        await db.refresh(user)
        return user
        
    except Exception as e:
        # Clean up if failed
        if os.path.exists(photo_path):
            os.remove(photo_path)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process image: {str(e)}")
