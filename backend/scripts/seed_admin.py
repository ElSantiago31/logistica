"""Seed superadmin user — wrapper del script unificado.

Uso directo:
    python -m scripts.seed admin
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.services.auth import hash_password


async def main():
    engine = create_async_engine(settings.effective_database_url)
    S = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with S() as db:
        pw_hash = hash_password('Admin123!')
        result = await db.execute(text(
            """INSERT INTO users (id, email, password_hash, first_name, last_name, phone, document_type, document_number, user_type, is_verified, is_approved, is_active)
            VALUES (gen_random_uuid(), :email, :pw, 'Admin', 'Sistema', '3000000000', 'CC', '00000000', 'superadmin', true, true, true)
            ON CONFLICT (email) DO NOTHING"""
        ), {'email': 'admin@logistica.com', 'pw': pw_hash})
        await db.commit()
        if result.rowcount > 0:
            print('Superadmin created: admin@logistica.com / Admin123!')
        else:
            print('Superadmin ya existe: admin@logistica.com')
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())