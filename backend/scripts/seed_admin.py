"""Seed superadmin user."""
import asyncio
import sys
sys.path.insert(0, r'c:\Users\Karen\Downloads\logistica\backend')

from app.services.auth import hash_password
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

async def main():
    e = create_async_engine('postgresql+asyncpg://logistica:logistica_dev_2024@localhost:5432/logistica')
    S = sessionmaker(e, class_=AsyncSession, expire_on_commit=False)
    async with S() as db:
        pw_hash = hash_password('Admin123!')
        await db.execute(text(
            """INSERT INTO users (id, email, password_hash, first_name, last_name, phone, document_type, document_number, user_type, is_verified, is_approved, is_active)
            VALUES (gen_random_uuid(), :email, :pw, 'Admin', 'Sistema', '3000000000', 'CC', '00000000', 'superadmin', true, true, true)
            ON CONFLICT (email) DO NOTHING"""
        ), {'email': 'admin@logistica.com', 'pw': pw_hash})
        await db.commit()
        print('Superadmin created: admin@logistica.com / Admin123!')
    await e.dispose()

asyncio.run(main())