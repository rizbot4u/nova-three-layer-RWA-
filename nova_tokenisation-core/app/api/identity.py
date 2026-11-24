from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.investor import Investor
from app.schemas.investor import InvestorCreate, InvestorOut
from app.services.aml_service import aml_service
from app.services.kyc_service import kyc_service

router = APIRouter(prefix="/api/v1/identity", tags=["identity"])

@router.post("/investors", response_model=InvestorOut, status_code=201)
async def create_investor(payload: InvestorCreate, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(Investor).where(Investor.email == payload.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Investor already exists")
    investor = Investor(**payload.model_dump())
    db.add(investor)
    await db.commit()
    await db.refresh(investor)
    kyc = await kyc_service.verify_identity(str(investor.id), investor.full_name, investor.country)
    aml = await aml_service.screen_investor(str(investor.id), investor.country)
    investor.kyc_status = kyc["status"]
    investor.aml_risk_score = aml["risk_score"]
    await db.commit()
    await db.refresh(investor)
    return investor

@router.get("/investors/{investor_id}", response_model=InvestorOut)
async def get_investor(investor_id: UUID, db: AsyncSession = Depends(get_db)):
    investor = await db.get(Investor, investor_id)
    if not investor:
        raise HTTPException(status_code=404, detail="Investor not found")
    return investor
