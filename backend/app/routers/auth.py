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
    """Authenticate user and return JWT tokens."""
    user = await authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
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
    # Check if email already exists
    existing = await db.execute(
        select(User).where(User.email == request.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo electrónico ya está registrado",
        )

    # Check if document number already exists
    existing = await db.execute(
        select(User).where(User.document_number == request.document_number)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El número de documento ya está registrado",
        )

    # Create user
    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        first_name=request.first_name,
        last_name=request.last_name,
        phone=request.phone,
        document_type=request.document_type,
        document_number=request.document_number,
        user_type="operator",
        is_verified=False,
        is_approved=False,
    )
    db.add(user)
    await db.flush()

    # Create operator profile
    operator = Operator(
        user_id=user.id,
        eps_id=request.eps_id,
        arl_id=request.arl_id,
        city=request.city,
        blood_type=request.blood_type,
        emergency_contact_name=request.emergency_contact_name,
        emergency_contact_phone=request.emergency_contact_phone,
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
        message="Registro exitoso. Pendiente de verificación y aprobación.",
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