"""Seed roles/cargos for the logistics system."""
import asyncio
import sys
sys.path.insert(0, r'c:\Users\Karen\Downloads\logistica\backend')

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ROLES = [
    ("Coordinador General", "coordinador_general", "Coordinación general del evento", None),
    ("Coordinador Grupos Operadores", "coordinador_grupos", "Coordinación de grupos de operadores", None),
    ("Operador Logístico", "operador_logistico", "Soporte logístico general", None),
    ("Coordinador de Emergencias", "coordinador_emergencias", "Coordinación de planes de emergencia", None),
    ("Brigadista de Emergencias", "brigadista", "Brigada de emergencias y primeros auxilios", None),
    ("Líder Seguridad – Bouncer", "lider_seguridad", "Líder del equipo de seguridad", None),
    ("Operador de Seguridad – Bouncer", "seguridad_bouncer", "Control de acceso y seguridad", None),
    ("Acomodador", "acomodador", "Acomodación y guía de asistentes", None),
    ("Protocolo", "protocolo", "Atención y protocolo institucional", None),
    ("PMT – Plan de Manejo de Tráfico", "pmt", "Plan de manejo de tráfico vehicular", None),
    ("Operador de Montaje", "montaje", "Montaje y desmontaje de infraestructura", None),
    ("Operador de Aseo", "aseo", "Limpieza y mantenimiento del evento", None),
]

async def main():
    e = create_async_engine('postgresql+asyncpg://logistica:logistica_dev_2024@localhost:5432/logistica')
    S = sessionmaker(e, class_=AsyncSession, expire_on_commit=False)
    async with S() as db:
        for name, slug, desc, rate in ROLES:
            await db.execute(text("""
                INSERT INTO roles (id, name, slug, description, base_rate, is_active)
                VALUES (gen_random_uuid(), :name, :slug, :desc, :rate, true)
                ON CONFLICT (slug) DO UPDATE SET name = :name, description = :desc
            """), {'name': name, 'slug': slug, 'desc': desc, 'rate': rate})
        await db.commit()
        print(f'OK: {len(ROLES)} roles insertados/actualizados')
        for r in ROLES:
            print(f'   - {r[0]}')
    await e.dispose()

asyncio.run(main())