"""Auth router — login, register, refresh, logout, change password."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.users import User
from app.models.operators import Operator
from app.models.audit import AuditLog
from app.schemas.auth import (
    LoginRequest, LoginResponse, UserBrief,
    RegisterRequest, RegisterResponse,
    RefreshTokenRequest,
    ChangePasswordRequest,
    OperatorRegisterRequest,
)
from app.services.auth import (
    hash_password, verify_password, authenticate_user,
    create_access_token, create_refresh_token,
    decode_token, revoke_token,
)
from app.dependencies.auth import get_current_user, get_current_active_user, require_superadmin

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _build_login_response(user: User) -> LoginResponse:
    """Build a LoginResponse with tokens and user data."""
    role_name = user.role.name if user.role else None
    access = create_access_token(user.id, user.email, user.user_type, role_name)
    refresh = create_refresh_token(user.id, user.email)

    return LoginResponse(
        access_token=access["token"],
        refresh_token=refresh["token"],
        token_type="bearer",
        expires_in=access["expires_in"],
        user=UserBrief(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            user_type=user.user_type,
            role_name=role_name,
        ),
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user by document number and return JWT tokens."""
    user = await authenticate_user(db, request.document_number, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Documento o contraseña incorrectos",
        )

    # Update last login
    user.last_login = datetime.now(timezone.utc).isoformat()
    await db.commit()

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="login",
        resource_type="user",
        resource_id=user.id,
        details="Login exitoso",
    )
    db.add(audit)
    await db.commit()

    return _build_login_response(user)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_operator(request: OperatorRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Public registration for operators (from landing page)."""
    # Check if email already exists (only active users)
    existing = await db.execute(
        select(User).where(User.email == request.email, User.is_active == True)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo electrónico ya está registrado",
        )

    # Check if document number already exists (only active users)
    existing = await db.execute(
        select(User).where(User.document_number == request.document_number, User.is_active == True)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El número de documento ya está registrado",
        )

    # Create user (auto-approved on registration)
    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        first_name=request.first_name,
        last_name=request.last_name,
        phone=request.phone,
        document_type=request.document_type,
        document_number=request.document_number,
        user_type="operator",
        is_verified=True,
        is_approved=True,
    )
    db.add(user)
    await db.flush()

    # Create operator profile
    import json
    operator = Operator(
        user_id=user.id,
        eps_id=request.eps_id,
        arl_id=request.arl_id,
        city=request.city,
        address=request.address,
        locality=request.locality,
        blood_type=request.blood_type,
        emergency_contact_name=request.emergency_contact_name,
        emergency_contact_phone=request.emergency_contact_phone,
        whatsapp=request.whatsapp,
        has_protocol_experience=request.has_protocol_experience,
        event_size_experience=request.event_size_experience,
        shoe_size=request.shoe_size,
        shirt_size=request.shirt_size,
        pants_size=request.pants_size,
        jacket_size=request.jacket_size,
        experience_roles=json.dumps([str(r) for r in request.experience_roles]) if request.experience_roles else None,
    )
    db.add(operator)

    # Audit log
    audit = AuditLog(
        action="register",
        resource_type="user",
        resource_id=user.id,
        details=f"Operador registrado: {request.email}",
    )
    db.add(audit)
    await db.commit()

    return RegisterResponse(
        id=user.id,
        email=user.email,
        message="Registro exitoso. Bienvenido al sistema.",
    )


@router.post("/refresh")
async def refresh_token(request: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token using a valid refresh token."""
    payload = decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido",
        )

    # Check if refresh token is revoked
    jti = payload.get("jti")
    if jti:
        from app.services.auth import is_token_revoked
        if await is_token_revoked(db, jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token revocado",
            )

    user_id = payload.get("sub")
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )

    # Revoke old refresh token
    if jti:
        await revoke_token(db, jti, user.id, reason="refresh")

    # Issue new tokens
    role_name = user.role.name if user.role else None
    access = create_access_token(user.id, user.email, user.user_type, role_name)
    refresh = create_refresh_token(user.id, user.email)

    return {
        "access_token": access["token"],
        "refresh_token": refresh["token"],
        "token_type": "bearer",
        "expires_in": access["expires_in"],
    }


@router.post("/logout")
async def logout(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout — revoke the current access token."""
    # We need to get the JTI from the current token
    # The dependency already validated it, so we extract from user context
    # For simplicity, we'll accept the token in the body or header
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Use /logout/token endpoint with the JTI",
    )


@router.post("/logout/{jti}")
async def logout_by_jti(
    jti: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific token by JTI."""
    await revoke_token(db, jti, user.id, reason="logout")

    audit = AuditLog(
        user_id=user.id,
        action="logout",
        resource_type="user",
        resource_id=user.id,
    )
    db.add(audit)
    await db.commit()

    return {"message": "Sesión cerrada exitosamente"}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Change password for the current user."""
    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contraseña actual incorrecta",
        )

    if request.new_password != request.confirm_new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las contraseñas nuevas no coinciden",
        )

    user.password_hash = hash_password(request.new_password)
    await db.commit()

    audit = AuditLog(
        user_id=user.id,
        action="change_password",
        resource_type="user",
        resource_id=user.id,
    )
    db.add(audit)
    await db.commit()

    return {"message": "Contraseña actualizada exitosamente"}


# --- Superadmin: Manage Admins ---
@router.post("/admins", status_code=status.HTTP_201_CREATED)
async def create_admin(
    request: dict,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new admin/coordinator user. Superadmin only."""
    required = ["first_name", "last_name", "document_number", "password"]
    for f in required:
        if not request.get(f):
            raise HTTPException(status_code=400, detail=f"Campo requerido: {f}")

    # Check duplicate document
    existing = await db.execute(
        select(User).where(User.document_number == request["document_number"])
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="El número de documento ya está registrado")

    # Check duplicate email if provided
    if request.get("email"):
        existing = await db.execute(
            select(User).where(User.email == request["email"])
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="El correo electrónico ya está registrado")

    user_type = request.get("user_type", "coordinator")
    if user_type not in ("superadmin", "coordinator"):
        user_type = "coordinator"

    user = User(
        email=request.get("email", f"{request['document_number']}@logistica.local"),
        password_hash=hash_password(request["password"]),
        first_name=request["first_name"],
        last_name=request["last_name"],
        phone=request.get("phone"),
        document_type=request.get("document_type", "CC"),
        document_number=request["document_number"],
        user_type=user_type,
        is_verified=True,
        is_approved=True,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    audit = AuditLog(user_id=current_user.id, action="create_admin", resource_type="user", resource_id=user.id, details=f"Admin creado: {user.first_name} {user.last_name}")
    db.add(audit)
    await db.commit()

    return {"id": str(user.id), "message": "Administrador creado exitosamente"}


@router.get("/admins")
async def list_admins(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """List all admin users. Superadmin only."""
    result = await db.execute(
        select(User).where(User.user_type.in_(["superadmin", "coordinator"])).order_by(User.created_at.desc())
    )
    admins = result.scalars().all()
    return [{"id": str(a.id), "email": a.email, "first_name": a.first_name, "last_name": a.last_name,
             "document_number": a.document_number, "phone": a.phone, "user_type": a.user_type,
             "is_active": a.is_active, "last_login": str(a.last_login) if a.last_login else None} for a in admins]


@router.put("/admins/{admin_id}")
async def update_admin(
    admin_id: uuid.UUID,
    request: dict,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Update an admin user. Superadmin only."""
    result = await db.execute(select(User).where(User.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    for field in ["first_name", "last_name", "phone", "user_type", "is_active"]:
        if field in request:
            setattr(admin, field, request[field])

    if request.get("password"):
        admin.password_hash = hash_password(request["password"])

    await db.commit()
    return {"message": "Administrador actualizado"}


@router.delete("/admins/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin(
    admin_id: uuid.UUID,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate an admin user. Superadmin only. Cannot delete self."""
    if admin_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo")

    result = await db.execute(select(User).where(User.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    admin.is_active = False
    await db.commit()


@router.get("/me", response_model=UserBrief)
async def get_me(user: User = Depends(get_current_active_user)):
    """Get current user info."""
    role_name = user.role.name if user.role else None
    return UserBrief(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        user_type=user.user_type,
        role_name=role_name,
    )