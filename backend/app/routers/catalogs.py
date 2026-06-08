from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.eps import EPS
from app.models.arl import ARL
from app.models.roles import Role

router = APIRouter(prefix="/api/catalogs", tags=["Catalogs"])

@router.get("/eps")
async def list_eps(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EPS).where(EPS.is_active == True).order_by(EPS.name))
    return [{"id": str(e.id), "name": e.name, "code": e.code} for e in result.scalars().all()]

@router.get("/arl")
async def list_arl(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ARL).where(ARL.is_active == True).order_by(ARL.name))
    return [{"id": str(a.id), "name": a.name, "code": a.code} for a in result.scalars().all()]

@router.get("/roles")
async def list_roles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role).where(Role.is_active == True).order_by(Role.name))
    return [{"id": str(r.id), "name": r.name, "slug": r.slug} for r in result.scalars().all()]
