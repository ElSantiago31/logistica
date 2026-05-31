"""Authentication service — JWT tokens, password hashing, validation."""
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.users import User
from app.models.audit import RevokedToken

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- Password utilities ---
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# --- JWT utilities ---
def create_access_token(user_id: uuid.UUID, email: str, user_type: str, role_name: str | None = None) -> dict:
    """Create access token and return dict with token + expiry."""
    jti = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "role": user_type,
        "role_name": role_name,
        "jti": jti,
        "exp": expires,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return {
        "token": token,
        "jti": jti,
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def create_refresh_token(user_id: uuid.UUID, email: str) -> dict:
    """Create refresh token."""
    jti = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "refresh",
        "jti": jti,
        "exp": expires,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return {
        "token": token,
        "jti": jti,
    }


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


async def is_token_revoked(db: AsyncSession, jti: str) -> bool:
    """Check if a token has been revoked."""
    result = await db.execute(
        select(RevokedToken).where(RevokedToken.token_jti == jti)
    )
    return result.scalar_one_or_none() is not None


async def revoke_token(db: AsyncSession, jti: str, user_id: uuid.UUID, reason: str = "logout") -> None:
    """Revoke a token by adding it to the revoked tokens table."""
    revoked = RevokedToken(
        token_jti=jti,
        user_id=user_id,
        revoked_at=datetime.now(timezone.utc),
        reason=reason,
    )
    db.add(revoked)
    await db.commit()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    """Authenticate a user by email and password. Returns User or None."""
    result = await db.execute(
        select(User).where(User.email == email, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user