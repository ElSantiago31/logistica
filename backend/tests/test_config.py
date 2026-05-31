import pytest
from app.config import Settings


def test_settings_loads_from_env(app_settings):
    """Test that settings are loaded correctly from .env file."""
    assert app_settings.APP_NAME is not None
    assert app_settings.APP_VERSION is not None
    assert app_settings.JWT_SECRET_KEY is not None
    assert app_settings.JWT_ALGORITHM == "HS256"


def test_settings_defaults():
    """Test that default values are correct (when no .env overrides)."""
    s = Settings(_env_file=None)  # Skip .env to test defaults
    assert "Logistica" in s.APP_NAME
    assert s.APP_VERSION == "1.0.0"
    assert s.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 15
    assert s.JWT_REFRESH_TOKEN_EXPIRE_DAYS == 7
    assert s.PHOTO_MAX_SIZE_MB == 5


def test_allowed_origins_list(app_settings):
    """Test that CORS origins are parsed correctly from comma-separated string."""
    origins = app_settings.allowed_origins_list
    assert isinstance(origins, list)
    assert len(origins) >= 1
    assert all(isinstance(o, str) for o in origins)


def test_effective_database_url(app_settings):
    """Test that database URL is constructed correctly."""
    url = app_settings.effective_database_url
    assert url.startswith("postgresql+asyncpg://")
    assert "logistica" in url


def test_effective_test_database_url(app_settings):
    """Test that test database URL is constructed correctly."""
    url = app_settings.effective_test_database_url
    assert url.startswith("postgresql+asyncpg://")
    assert "test" in url


def test_jwt_settings(app_settings):
    """Test JWT configuration values."""
    assert app_settings.JWT_ALGORITHM in ["HS256", "HS384", "HS512"]
    assert app_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES > 0
    assert app_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS > 0


def test_photo_settings(app_settings):
    """Test photo storage configuration."""
    assert app_settings.PHOTOS_DIR is not None
    assert app_settings.PHOTOS_THUMBNAIL_DIR is not None
    assert app_settings.PHOTO_MAX_SIZE_MB > 0