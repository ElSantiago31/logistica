from pydantic import model_validator
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

    # JWT — vacío por defecto: fail-safe si falta la variable de entorno en producción
    JWT_SECRET_KEY: str = ""
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

    # App — DEBUG=False por defecto (fail-safe: producción segura salvo que se indique lo contrario)
    APP_NAME: str = "Logistica"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ALLOWED_ORIGINS: str = "http://localhost:8000"

    # JS_SUFFIX se deriva AUTOMÁTICAMENTE de DEBUG (fail-safe):
    #   - DEBUG=True  → ""     (sirve auth.js legible, ideal para depurar en dev)
    #   - DEBUG=False → ".min" (sirve auth.min.js minificado/ofuscado en prod)
    # Se puede sobreescribir explícitamente con JS_SUFFIX en .env, pero si queda
    # vacío, la regla de DEBUG prevalece para evitar exponer código legible en prod.
    JS_SUFFIX: str = ""

    # Feature flags
    FEATURE_PAYROLL_ENABLED: bool = True

    # Photos
    PHOTOS_DIR: str = "./data/photos"
    PHOTOS_THUMBNAIL_DIR: str = "./data/photos/thumbnails"
    PHOTO_MAX_SIZE_MB: int = 5

    # RUT (Registro Único Tributario) — PDF obligatorio en el registro
    RUT_DIR: str = "./data/rut"
    RUT_MAX_SIZE_MB: int = 5
    # Compresión del PDF del RUT
    RUT_COMPRESS_DPI: int = 150
    RUT_COMPRESS_QUALITY: int = 75

    # pgAdmin — password vacío por defecto (fail-safe)
    PGADMIN_EMAIL: str = "admin@logistica.com"
    PGADMIN_PASSWORD: str = ""
    PGADMIN_PORT: int = 5050

    @model_validator(mode="after")
    def _derive_js_suffix(self):
        """Deriva JS_SUFFIX automáticamente de DEBUG si no se seteó explícitamente.

        Fail-safe: en producción (DEBUG=False) sin JS_SUFFIX, fuerza ".min" para
        servir siempre los assets minificados/ofuscados, evitando exponer código
        JS legible con comentarios y nombres de variables en el navegador.
        """
        if not self.JS_SUFFIX:
            # Solo setear el sufijo si los .min.js existen en el directorio JS.
            # Evita 404 en entornos donde no se ejecutó `npm run build`.
            import os
            _js_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "..", "frontend", "js",
            )
            _has_min = os.path.isdir(_js_dir) and any(
                f.endswith(".min.js") for f in os.listdir(_js_dir)
            )
            self.JS_SUFFIX = ".min" if (not self.DEBUG and _has_min) else ""
        return self

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

    # Placeholders conocidos que NUNCA deben usarse en producción
    _INSECURE_JWT_PLACEHOLDERS = frozenset({
        "",
        "change-me-in-production",
        "changeme",
        "secret",
    })

    def validate_for_production(self) -> None:
        """Fail-safe: impide arrancar en producción con secretos débiles o ausentes.

        Se invoca al importar el módulo. Si DEBUG=False (producción) y el
        JWT_SECRET_KEY está vacío o es un placeholder conocido, lanza RuntimeError
        con un mensaje claro en lugar de arrancar con un secreto predecible.
        """
        if self.DEBUG:
            return
        if self.JWT_SECRET_KEY in self._INSECURE_JWT_PLACEHOLDERS:
            raise RuntimeError(
                "JWT_SECRET_KEY no está configurado o usa un valor inseguro. "
                "Genera uno con: python -c \"import secrets; print(secrets.token_hex(32))\" "
                "y defínelo en el archivo .env antes de arrancar en producción."
            )


settings = Settings()
settings.validate_for_production()
