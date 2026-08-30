from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings


# Async engine for application database
engine = create_async_engine(
    settings.effective_database_url,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# Async engine for test database (lazy, used by test fixtures)
test_engine = None


def get_test_engine():
    global test_engine
    if test_engine is None:
        test_engine = create_async_engine(
            settings.effective_test_database_url,
            echo=settings.DEBUG,
            # NullPool: cada operación abre/cierra su conexión. Evita que
            # conexiones del pool queden atadas a un event loop distinto
            # cuando pytest-asyncio crea un loop nuevo por test.
            poolclass=NullPool,
        )
    return test_engine


# Session factories
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db() -> AsyncSession:
    """Dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_test_db() -> AsyncSession:
    """Dependency that yields an async test database session."""
    test_async_session = async_sessionmaker(
        get_test_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with test_async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()