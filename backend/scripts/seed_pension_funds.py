"""Seed Fondos de Pensión — wrapper del script unificado.

Uso directo:
    python -m scripts.seed pension-funds
"""
from app.config import settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from scripts.seed import PENSION_FUNDS


async def main():
    engine = create_async_engine(settings.effective_database_url)
    S = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with S() as db:
        await db.execute(text("UPDATE pension_fund SET is_active = false"))
        for name, code in PENSION_FUNDS:
            await db.execute(text("""
                INSERT INTO pension_fund (id, name, code, is_active)
                VALUES (gen_random_uuid(), :name, :code, true)
                ON CONFLICT (code) DO UPDATE SET name = :name, is_active = true
            """), {'name': name, 'code': code})
        await db.commit()
        print(f'OK: {len(PENSION_FUNDS)} Fondos de Pensión insertados/actualizados')
        for name, code in PENSION_FUNDS:
            print(f'   - {name} ({code})')

    await engine.dispose()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())