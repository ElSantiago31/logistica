from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "logistica"
    POSTGRES_USER: str = "logistica"
    POSTGRES_PASSWORD: str = "logistica_dev_2024"
    DATABASE_URL: str = ""
    TEST_DATABASE_URL: str = ""

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Zenvia WhatsApp API
    ZENVIA_API_KEY: str = ""
    ZENVIA_API_URL: str = "https://api.zenvia.com/v2"
    ZENVIA_CHANNEL_ID: str = ""
    ZENVIA_WEBHOOK_TOKEN: str = ""

    # Zenvia template names (must match templates created in Zenvia dashboard)
    ZENVIA_TEMPLATE_INVITATION: str = "event_invitation"
    ZENVIA_TEMPLATE_REMINDER_1D: str = "reminder_1d"
    ZENVIA_TEMPLATE_REMINDER_5D: str = "reminder_5d"

    # Confirmation keywords (operators text these to confirm/reject via WhatsApp)
    ZENVIA_CONFIRM_KEYWORDS: str = "CONFIRMAR,SI,SÍ,CONFIRMO,CONFIRM"
    ZENVIA_REJECT_KEYWORDS: str = "RECHAZAR,NO,RECHAZO,REJECT"

    # App
    APP_NAME: str = "Logistica"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:8000"

    # Feature flags
    FEATURE_PAYROLL_ENABLED: bool = True

    # Photos
    PHOTOS_DIR: str = "./data/photos"
    PHOTOS_THUMBNAIL_DIR: str = "./data/photos/thumbnails"
    PHOTO_MAX_SIZE_MB: int = 5

    # pgAdmin
    PGADMIN_EMAIL: str = "admin@logistica.com"
    PGADMIN_PASSWORD: str = "admin123"
    PGADMIN_PORT: int = 5050

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    @property
    def effective_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def effective_test_database_url(self) -> str:
        if self.TEST_DATABASE_URL:
            return self.TEST_DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}_test"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()