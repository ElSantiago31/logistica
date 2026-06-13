"""Seed inicial unificado: roles, ARLs y superadmin.

Uso:
    python -m scripts.seed            # todo
    python -m scripts.seed roles      # solo roles
    python -m scripts.seed arls       # solo ARLs
    python -m scripts.seed admin      # solo superadmin
"""
import asyncio
import sys
import os

# Asegurar que el directorio backend/ esté en sys.path sin hardcodear rutas
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.services.auth import hash_password


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


def get_engine():
    url = settings.effective_database_url
    return create_async_engine(url)


async def seed_roles(db: AsyncSession):
    for name, slug, desc, rate in ROLES:
        await db.execute(text("""
            INSERT INTO roles (id, name, slug, description, base_rate, is_active)
            VALUES (gen_random_uuid(), :name, :slug, :desc, :rate, true)
            ON CONFLICT (slug) DO UPDATE SET name = :name, description = :desc
        """), {'name': name, 'slug': slug, 'desc': desc, 'rate': rate})
    print(f'OK: {len(ROLES)} roles insertados/actualizados')


async def seed_arls(db: AsyncSession):
    await db.execute(text("UPDATE arl SET is_active = false"))
    for name, code in ARLS:
        await db.execute(text("""
            INSERT INTO arl (id, name, code, is_active)
            VALUES (gen_random_uuid(), :name, :code, true)
            ON CONFLICT (code) DO UPDATE SET name = :name, is_active = true
        """), {'name': name, 'code': code})
    print(f'OK: {len(ARLS)} ARLs insertadas/actualizadas')


async def seed_admin(db: AsyncSession):
    pw_hash = hash_password('Admin123!')
    result = await db.execute(text(
        """INSERT INTO users (id, email, password_hash, first_name, last_name, phone, document_type, document_number, user_type, is_verified, is_approved, is_active)
        VALUES (gen_random_uuid(), :email, :pw, 'Admin', 'Sistema', '3000000000', 'CC', '00000000', 'superadmin', true, true, true)
        ON CONFLICT (email) DO NOTHING"""
    ), {'email': 'admin@logistica.com', 'pw': pw_hash})
    if result.rowcount > 0:
        print('OK: Superadmin creado -> admin@logistica.com / Admin123!')
    else:
        print('OK: Superadmin ya existe (admin@logistica.com)')


async def main():
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    engine = get_engine()
    S = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with S() as db:
        if only in ("all", "roles"):
            await seed_roles(db)
        if only in ("all", "arls"):
            await seed_arls(db)
        if only in ("all", "admin"):
            await seed_admin(db)
        await db.commit()
    await engine.dispose()
    print("Seed completado.")


if __name__ == "__main__":
    asyncio.run(main())