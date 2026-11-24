from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.share_holding import ShareHolding
from app.schemas.share_holding import ShareHoldingOut, ShareIssue
from app.services.tokenisation_service import tokenisation_service

router = APIRouter(prefix="/api/v1/shares", tags=["shares"])

@router.post("/issue", response_model=ShareHoldingOut, status_code=201)
async def issue_shares(payload: ShareIssue, db: AsyncSession = Depends(get_db)):
    try:
        holding = await tokenisation_service.issue_shares(
            db, payload.property_id, payload.investor_id, payload.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return holding

@router.get("/holdings/{investor_id}", response_model=list[ShareHoldingOut])
async def get_holdings(investor_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ShareHolding).where(ShareHolding.investor_id == investor_id))
    return result.scalars().all()
