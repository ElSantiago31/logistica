"""Tests for auth services — JWT tokens, password hashing, validation."""
import uuid
import pytest

from app.services.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token,
)
from app.config import settings


class TestPasswordHashing:
    def test_hash_password(self):
        hashed = hash_password("Test123!")
        assert hashed != "Test123!"
        assert len(hashed) > 20

    def test_verify_password_correct(self):
        hashed = hash_password("Test123!")
        assert verify_password("Test123!", hashed) is True

    def test_verify_password_incorrect(self):
        hashed = hash_password("Test123!")
        assert verify_password("WrongPassword", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("Test123!")
        h2 = hash_password("Test123!")
        assert h1 != h2  # bcrypt uses random salt


class TestJWTTokens:
    def test_create_access_token(self):
        user_id = uuid.uuid4()
        result = create_access_token(user_id, "test@test.com", "superadmin")
        assert "token" in result
        assert "jti" in result
        assert "expires_in" in result
        assert result["expires_in"] == settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    def test_create_refresh_token(self):
        user_id = uuid.uuid4()
        result = create_refresh_token(user_id, "test@test.com")
        assert "token" in result
        assert "jti" in result

    def test_decode_access_token(self):
        user_id = uuid.uuid4()
        result = create_access_token(user_id, "test@test.com", "operator", "Bouncer")
        payload = decode_token(result["token"])
        assert payload is not None
        assert payload["sub"] == str(user_id)
        assert payload["email"] == "test@test.com"
        assert payload["type"] == "access"
        assert payload["role"] == "operator"
        assert payload["role_name"] == "Bouncer"
        assert "jti" in payload
        assert "exp" in payload

    def test_decode_refresh_token(self):
        user_id = uuid.uuid4()
        result = create_refresh_token(user_id, "test@test.com")
        payload = decode_token(result["token"])
        assert payload is not None
        assert payload["type"] == "refresh"

    def test_decode_invalid_token(self):
        payload = decode_token("invalid.token.here")
        assert payload is None

    def test_decode_expired_token(self):
        # Manually create an expired token
        from jose import jwt
        from datetime import datetime, timedelta, timezone
        expired_payload = {
            "sub": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "type": "access",
            "jti": str(uuid.uuid4()),
        }
        expired_token = jwt.encode(expired_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        payload = decode_token(expired_token)
        assert payload is None

    def test_token_has_unique_jti(self):
        user_id = uuid.uuid4()
        t1 = create_access_token(user_id, "test@test.com", "admin")
        t2 = create_access_token(user_id, "test@test.com", "admin")
        assert t1["jti"] != t2["jti"]


class TestSchemas:
    def test_login_request_validation(self):
        from app.schemas.auth import LoginRequest
        req = LoginRequest(email="test@test.com", password="123456")
        assert req.email == "test@test.com"

    def test_login_request_invalid_email(self):
        from pydantic import ValidationError
        from app.schemas.auth import LoginRequest
        with pytest.raises(ValidationError):
            LoginRequest(email="not-an-email", password="123456")

    def test_register_request_password_too_short(self):
        from pydantic import ValidationError
        from app.schemas.auth import OperatorRegisterRequest
        with pytest.raises(ValidationError):
            OperatorRegisterRequest(
                email="test@test.com",
                password="short",
                first_name="Test",
                last_name="User",
                phone="3001234567",
                document_number="12345678",
            )

    def test_change_password_validation(self):
        from pydantic import ValidationError
        from app.schemas.auth import ChangePasswordRequest
        with pytest.raises(ValidationError):
            ChangePasswordRequest(
                current_password="a",  # too short
                new_password="NewPass123!",
                confirm_new_password="NewPass123!",
            )