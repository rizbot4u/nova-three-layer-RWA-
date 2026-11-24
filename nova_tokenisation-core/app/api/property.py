from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.property import Property
from app.schemas.property import PropertyCreate, PropertyOut
from app.utils.audit import write_audit_event

router = APIRouter(prefix="/api/v1/property", tags=["property"])

@router.post("/properties", response_model=PropertyOut, status_code=201)
async def create_property(payload: PropertyCreate, db: AsyncSession = Depends(get_db)):
    prop = Property(**payload.model_dump(), status="draft")
    db.add(prop)
    await db.commit()
    await db.refresh(prop)
    await write_audit_event("property.created", {"property_id": str(prop.id)})
    return prop

@router.post("/properties/{property_id}/activate", response_model=PropertyOut)
async def activate_property(property_id: UUID, db: AsyncSession = Depends(get_db)):
    prop = await db.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    prop.status = "active"
    await db.commit()
    await db.refresh(prop)
    await write_audit_event("property.activated", {"property_id": str(prop.id)})
    return prop

@router.get("/properties/{property_id}", response_model=PropertyOut)
async def get_property(property_id: UUID, db: AsyncSession = Depends(get_db)):
    prop = await db.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop
