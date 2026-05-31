"""Seed script — populate database with initial catalog data and superadmin."""
import asyncio
import sys
import os
from getpass import getpass

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from passlib.context import CryptContext

from app.config import settings
from app.database import async_session, engine, Base
from app.models import Role, EPS, ARL, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed_catalogs():
    """Seed catalog tables: roles, EPS, ARL."""
    async with async_session() as session:
        # --- Roles ---
        roles_data = [
            {"name": "Bouncer", "slug": "bouncer", "description": "Seguridad y control de acceso", "base_rate": 80000},
            {"name": "Acomodador", "slug": "acomodador", "description": "Ubicación y guía del público", "base_rate": 60000},
            {"name": "Logístico", "slug": "logistico", "description": "Montaje, desmontaje y soporte logístico", "base_rate": 70000},
            {"name": "Coordinador de Piso", "slug": "coordinador_piso", "description": "Coordinación de personal en sitio", "base_rate": 120000},
            {"name": "Coordinador General", "slug": "coordinador_general", "description": "Dirección general del evento", "base_rate": 200000},
            {"name": "Azafata/o", "slug": "azafata", "description": "Atención e información al público", "base_rate": 70000},
            {"name": "Técnico", "slug": "tecnico", "description": "Soporte técnico y audiovisual", "base_rate": 100000},
            {"name": "Producción", "slug": "produccion", "description": "Apoyo en producción del evento", "base_rate": 90000},
        ]

        for role_data in roles_data:
            existing = await session.execute(
                Role.__table__.select().where(Role.__table__.c.slug == role_data["slug"])
            )
            if not existing.first():
                await session.execute(Role.__table__.insert().values(**role_data))
                print(f"  ✅ Rol creado: {role_data['name']}")
            else:
                print(f"  ⏭️  Rol ya existe: {role_data['name']}")

        # --- EPS ---
        eps_data = [
            {"name": "Sanitas", "code": "EPS017", "nit": "800088702"},
            {"name": "Nueva EPS", "code": "EPS019", "nit": "900156264"},
            {"name": "Sura", "code": "EPS020", "nit": "890102049"},
            {"name": "Saludvida", "code": "EPS021", "nit": "900096847"},
            {"name": "Famisanar", "code": "EPS018", "nit": "860042422"},
            {"name": "Coomeva", "code": "EPS016", "nit": "890107059"},
            {"name": "Compensar", "code": "EPS022", "nit": "860027432"},
            {"name": "Medimás", "code": "EPS024", "nit": "900491542"},
        ]

        for eps in eps_data:
            existing = await session.execute(
                EPS.__table__.select().where(EPS.__table__.c.name == eps["name"])
            )
            if not existing.first():
                await session.execute(EPS.__table__.insert().values(**eps))
                print(f"  ✅ EPS creada: {eps['name']}")
            else:
                print(f"  ⏭️  EPS ya existe: {eps['name']}")

        # --- ARL ---
        arl_data = [
            {"name": "Positiva", "code": "ARL001", "nit": "890102049"},
            {"name": "Colpatria", "code": "ARL002", "nit": "860027432"},
            {"name": "Bolívar", "code": "ARL003", "nit": "890102049"},
            {"name": "Sura", "code": "ARL004", "nit": "890102049"},
            {"name": "Equidad", "code": "ARL005", "nit": "860027432"},
            {"name": "Colmena", "code": "ARL006", "nit": "890102049"},
            {"name": "La Previsora", "code": "ARL007", "nit": "860027432"},
        ]

        for arl in arl_data:
            existing = await session.execute(
                ARL.__table__.select().where(ARL.__table__.c.name == arl["name"])
            )
            if not existing.first():
                await session.execute(ARL.__table__.insert().values(**arl))
                print(f"  ✅ ARL creada: {arl['name']}")
            else:
                print(f"  ⏭️  ARL ya existe: {arl['name']}")

        await session.commit()


async def seed_superadmin():
    """Create the superadmin user."""
    async with async_session() as session:
        # Check if superadmin already exists
        existing = await session.execute(
            User.__table__.select().where(User.__table__.c.user_type == "superadmin")
        )
        if existing.first():
            print("  ⏭️  Superadmin ya existe, saltando...")
            return

        email = os.environ.get("ADMIN_EMAIL", "admin@logistica.com")
        password = os.environ.get("ADMIN_PASSWORD", "Admin123!")

        password_hash = pwd_context.hash(password)

        await session.execute(
            User.__table__.insert().values(
                email=email,
                password_hash=password_hash,
                first_name="Super",
                last_name="Administrador",
                phone="3000000000",
                user_type="superadmin",
                is_verified=True,
                is_approved=True,
                is_active=True,
            )
        )
        await session.commit()
        print(f"  ✅ Superadmin creado: {email} / {password}")


async def main():
    """Run all seed functions."""
    print("\n🌱 Iniciando seed de base de datos...\n")
    print(f"📡 Database: {settings.effective_database_url.split('@')[-1]}\n")

    # Create all tables first (in case alembic hasn't run)
    print("📋 Creando tablas si no existen...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("  ✅ Tablas verificadas\n")

    print("📂 Seed de catálogos:")
    await seed_catalogs()
    print()

    print("👤 Seed de superadmin:")
    await seed_superadmin()
    print()

    print("✅ Seed completado exitosamente!\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())