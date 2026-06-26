import json
import os
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.eps import EPS
from app.models.arl import ARL
from app.models.roles import Role

router = APIRouter(prefix="/api/catalogs", tags=["Catalogs"])

# Load Colombia cities from local JSON (cached)
_cities_cache = None

def _load_cities():
    global _cities_cache
    if _cities_cache is None:
        cities_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'colombia_cities.json')
        with open(cities_path, 'r', encoding='utf-8') as f:
            _cities_cache = json.load(f)
    return _cities_cache

@router.get("/cities")
async def list_cities():
    """Returns departments and cities of Colombia from local DIVIPOLA data."""
    return _load_cities()

@router.get("/eps")
async def list_eps(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EPS).where(EPS.is_active == True).order_by(EPS.name))
    return [{"id": str(e.id), "name": e.name, "code": e.code} for e in result.scalars().all()]

@router.get("/arl")
async def list_arl(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ARL).where(ARL.is_active == True).order_by(ARL.name))
    return [{"id": str(a.id), "name": a.name, "code": a.code} for a in result.scalars().all()]

@router.get("/roles")
async def list_roles(
    include_event_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Lista roles.

    Por defecto (include_event_only=False) excluye los roles exclusivos de
    eventos (is_event_only=true), de modo que el formulario de registro /
    edición de operador nunca los muestre. Los flujos de creación/edición de
    evento pasan include_event_only=true para ver todos los roles.
    """
    query = select(Role).where(Role.is_active == True)
    if not include_event_only:
        query = query.where(Role.is_event_only == False)
    result = await db.execute(query.order_by(Role.name))
    return [{"id": str(r.id), "name": r.name, "slug": r.slug} for r in result.scalars().all()]
