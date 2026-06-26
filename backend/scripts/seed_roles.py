"""Seed roles/cargos — wrapper del script unificado.

Uso directo:
    python -m scripts.seed roles
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from scripts.seed import ROLES


async def main():
    engine = create_async_engine(settings.effective_database_url)
    S = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with S() as db:
        for name, slug, desc, rate, level, area, is_event_only in ROLES:
            await db.execute(text("""
                INSERT INTO roles (id, name, slug, description, base_rate, hierarchy_level, area, is_event_only, is_active)
                VALUES (gen_random_uuid(), :name, :slug, :desc, :rate, :level, :area, :is_event_only, true)
                ON CONFLICT (slug) DO UPDATE SET
                    name = :name, description = :desc,
                    hierarchy_level = :level, area = :area, is_event_only = :is_event_only
            """), {'name': name, 'slug': slug, 'desc': desc, 'rate': rate, 'level': level, 'area': area, 'is_event_only': is_event_only})
        await db.commit()
        print(f'OK: {len(ROLES)} roles insertados/actualizados (con jerarquía, área y event-only)')
        for r in ROLES:
            print(f'   - {r[0]} (nivel {r[4]})')
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())