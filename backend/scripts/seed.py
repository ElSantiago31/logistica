"""Seed inicial unificado: roles, ARLs, EPS y superadmin.

Uso:
    python -m scripts.seed            # todo
    python -m scripts.seed roles      # solo roles
    python -m scripts.seed arls       # solo ARLs
    python -m scripts.seed eps        # solo EPS
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


# Formato: (name, slug, description, base_rate, hierarchy_level, area, is_event_only)
# hierarchy_level: 1=Coordinador General, 2=Coordinador de área, 3=Operador
# area: categoría funcional (None para roles generales)
# is_event_only: True = rol exclusivo de eventos (NO aparece en registro de operadores)
ROLES = [
    # Nivel 1 — Coordinador General (event-only)
    ("Coordinador General", "coordinador_general", "Coordinación general del evento", None, 1, None, True),
    # Nivel 2 — Coordinadores de área (event-only)
    ("Coordinador Grupos Operadores", "coordinador_grupos", "Coordinación de grupos de operadores", None, 2, "Grupos", True),
    ("Coordinador de Emergencias", "coordinador_emergencias", "Coordinación de planes de emergencia", None, 2, "Emergencias", True),
    ("Líder Seguridad – Bouncer", "lider_seguridad", "Líder del equipo de seguridad", None, 2, "Seguridad", True),
    # Nivel 3 — Operadores (registrables)
    ("Operador Logístico", "operador_logistico", "Soporte logístico general", None, 3, "Logística", False),
    ("Brigadista de Emergencias", "brigadista", "Brigada de emergencias y primeros auxilios", None, 3, "Emergencias", False),
    ("Operador de Seguridad – Bouncer", "seguridad_bouncer", "Control de acceso y seguridad", None, 3, "Seguridad", False),
    ("Acomodador", "acomodador", "Acomodación y guía de asistentes", None, 3, None, False),
    ("Protocolo", "protocolo", "Atención y protocolo institucional", None, 3, None, False),
    ("PMT – Plan de Manejo de Tráfico", "pmt", "Plan de manejo de tráfico vehicular", None, 3, "Tráfico", False),
    ("Operador de Montaje", "montaje", "Montaje y desmontaje de infraestructura", None, 3, "Montaje", False),
    ("Operador de Aseo", "aseo", "Limpieza y mantenimiento del evento", None, 3, "Aseo", False),
    ("Universitario", "universitario", "Personal universitario cercano a artistas", None, 3, "Seguridad", False),
    # Nivel 3 — Roles event-only nuevos (reportan al Coordinador General)
    ("Coordinadores Externos", "coordinadores_externos", "Coordinación externa (reporta al Coordinador General)", None, 3, "Externa", True),
    ("Brigadista Externo", "brigadista_externo", "Brigada de emergencias externa (reporta al Coordinador General)", None, 3, "Externa", True),
    ("Personal Oficina", "personal_oficina", "Personal de oficina (reporta al Coordinador General)", None, 3, "Oficina", True),
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

# Lista oficial EPS vigentes en el Sistema de Seguridad Social en Salud (Colombia)
# Sin duplicados. Fuente: listado EPS activas (ADRES / MinSalud).
EPS_LIST = [
    ("Nueva EPS", "EPS-001"),
    ("EPS Sura", "EPS-002"),
    ("Sanitas EPS", "EPS-003"),
    ("Salud Total EPS", "EPS-004"),
    ("EPS Coomeva", "EPS-005"),
    ("Compensar EPS", "EPS-006"),
    ("Servicio Occidental de Salud - SOS EPS", "EPS-007"),
    ("Mutual Ser EPS", "EPS-008"),
    ("EPS Famisanar", "EPS-009"),
    ("Colsanitas EPS", "EPS-010"),
    ("Saludvida EPS", "EPS-011"),
    ("Capresoca EPS", "EPS-012"),
    ("Comfaoriente EPS", "EPS-013"),
    ("Comfacundi EPS", "EPS-014"),
    ("Comfamiliar Huila EPS", "EPS-015"),
    ("EPM EPS", "EPS-016"),
    ("Dusakawi EPS", "EPS-017"),
    ("Anas Wayúu EPS", "EPS-018"),
    ("Pijaos Salud EPS", "EPS-019"),
    ("Ambuq EPS", "EPS-020"),
    ("Capital Salud EPS", "EPS-021"),
    ("Comfachocó EPS", "EPS-022"),
    ("Comfa Sucre EPS", "EPS-023"),
    ("EPS Mallamas", "EPS-024"),
    ("Manexka EPS", "EPS-025"),
    ("ASMET Salud EPS", "EPS-026"),
    ("Emssanar EPS", "EPS-027"),
    ("EPS Sanitas (Régimen Subsidiado)", "EPS-028"),
    ("Solsalud EPS", "EPS-029"),
    ("Gold Trust EPS", "EPS-030"),
]


def get_engine():
    url = settings.effective_database_url
    return create_async_engine(url)


async def seed_roles(db: AsyncSession):
    for name, slug, desc, rate, level, area, is_event_only in ROLES:
        await db.execute(text("""
            INSERT INTO roles (id, name, slug, description, base_rate, hierarchy_level, area, is_event_only, is_active)
            VALUES (gen_random_uuid(), :name, :slug, :desc, :rate, :level, :area, :is_event_only, true)
            ON CONFLICT (slug) DO UPDATE SET
                name = :name, description = :desc,
                hierarchy_level = :level, area = :area, is_event_only = :is_event_only
        """), {'name': name, 'slug': slug, 'desc': desc, 'rate': rate, 'level': level, 'area': area, 'is_event_only': is_event_only})
    print(f'OK: {len(ROLES)} roles insertados/actualizados (con jerarquía, área y event-only)')


async def seed_arls(db: AsyncSession):
    await db.execute(text("UPDATE arl SET is_active = false"))
    for name, code in ARLS:
        await db.execute(text("""
            INSERT INTO arl (id, name, code, is_active)
            VALUES (gen_random_uuid(), :name, :code, true)
            ON CONFLICT (code) DO UPDATE SET name = :name, is_active = true
        """), {'name': name, 'code': code})
    print(f'OK: {len(ARLS)} ARLs insertadas/actualizadas')


async def seed_eps(db: AsyncSession):
    """Siembra/actualiza la lista de EPS (Entidades Promotoras de Salud)."""
    await db.execute(text("UPDATE eps SET is_active = false"))
    for name, code in EPS_LIST:
        await db.execute(text("""
            INSERT INTO eps (id, name, code, is_active)
            VALUES (gen_random_uuid(), :name, :code, true)
            ON CONFLICT (code) DO UPDATE SET name = :name, is_active = true
        """), {'name': name, 'code': code})
    print(f'OK: {len(EPS_LIST)} EPS insertadas/actualizadas')


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
        if only in ("all", "eps"):
            await seed_eps(db)
        if only in ("all", "admin"):
            await seed_admin(db)
        await db.commit()
    await engine.dispose()
    print("Seed completado.")


if __name__ == "__main__":
    asyncio.run(main())