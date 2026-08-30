import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import app
from app.config import settings
from app.database import Base, get_test_engine, get_db, get_test_db


async def _ensure_tables():
    """Crea las tablas en la BD de prueba (best-effort).

    Permite que el fixture ``client`` sea auto-contenido: las rutas que
    consultan la BD encuentran el esquema aunque el test no use ``db``.
    """
    engine = get_test_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
async def db():
    """Provides a database session for tests, creating and dropping all tables.

    Skips tests gracefully if the test database is not available (e.g. the
    ``logistica_test`` database hasn't been created yet).
    """
    engine = get_test_engine()

    # Create tables - skip the entire test if the DB is unreachable
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        pytest.skip(f"Test database not available: {exc}")

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()

    # Drop tables after test completes
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    except Exception:
        pass  # Best-effort cleanup


@pytest.fixture
async def client():
    """Async HTTP client for testing FastAPI endpoints."""
    # Ensure schema exists so DB-backed routes work even without the `db` fixture
    try:
        await _ensure_tables()
    except Exception:
        pass  # DB-backed tests will surface their own errors/skips

    # Override database dependency to use the test database
    app.dependency_overrides[get_db] = get_test_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def app_settings():
    """Return application settings for testing."""
    return settings
