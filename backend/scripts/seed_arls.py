"""Seed ARLs - Administradoras de Riesgos Laborales."""
import asyncio
import sys
sys.path.insert(0, r'c:\Users\Karen\Downloads\logistica\backend')

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ARLS = [
    ("ARL SURA", "ARL-SURA"),
    ("Positiva Compañía de Seguros", "POSITIVA"),
    ("ARL Colmena", "ARL-COLMENA"),
    ("AXA Colpatria", "AXA-COLPATRIA"),
    ("Seguros Bolívar", "SEGUROS-BOLIVAR"),
    ("MAPFRE", "MAPFRE"),
    ("Seguros Alfa", "SEGUROS-ALFA"),
    ("La Equidad Seguros", "EQUIDAD"),
    ("Aurora Seguros", "AURORA"),
    ("Colsanitas Seguros", "COLSANITAS"),
]

async def main():
    e = create_async_engine('postgresql+asyncpg://logistica:logistica_dev_2024@localhost:5432/logistica')
    S = sessionmaker(e, class_=AsyncSession, expire_on_commit=False)
    async with S() as db:
        # Desactivar todas las ARLs existentes primero
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
    await e.dispose()

asyncio.run(main())