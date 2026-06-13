"""Seed ARLs — wrapper del script unificado.

Uso directo:
    python -m scripts.seed arls
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from scripts.seed import ARLS


async def main():
    engine = create_async_engine(settings.effective_database_url)
    S = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with S() as db:
        await db.execute(text("UPDATE arl SET is_active = false"))
        for name, code in ARLS:
            await db.execute(text("""
                INSERT INTO arl (id, name, code, is_active)
                VALUES (gen_random_uuid(), :name, :code, true)
                ON CONFLICT (code) DO UPDATE SET name = :name, is_active = true
            """), {'name': name, 'code': code})
        await db.commit()
        print(f'OK: {len(ARLS)} ARLs insertadas/actualizadas')
        for name, code in ARLS:
            print(f'   - {name} ({code})')
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())