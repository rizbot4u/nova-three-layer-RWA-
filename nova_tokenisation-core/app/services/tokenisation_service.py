from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.property import Property
from app.models.share_holding import ShareHolding
from app.utils.audit import write_audit_event

class TokenisationService:
    async def issue_shares(self, db: AsyncSession, property_id: UUID, investor_id: UUID, amount: int) -> ShareHolding:
        prop = await db.get(Property, property_id)
        if not prop:
            raise ValueError("Property not found")
        if prop.status != "active":
            raise ValueError("Property is not active for issuance")
        if prop.circulating_supply + amount > prop.total_supply:
            raise ValueError("Exceeds fixed total supply — cannot mint more")

        holding = (await db.execute(
            select(ShareHolding).where(
                ShareHolding.property_id == property_id,
                ShareHolding.investor_id == investor_id,
            )
        )).scalar_one_or_none()

        if holding:
            holding.shares += amount
        else:
            holding = ShareHolding(property_id=property_id, investor_id=investor_id, shares=amount)
            db.add(holding)

        prop.circulating_supply += amount
        await db.commit()
        await db.refresh(holding)
        await write_audit_event("shares.issued", {
            "property_id": str(property_id),
            "investor_id": str(investor_id),
            "amount": amount,
            "new_circulating_supply": prop.circulating_supply,
        })
        return holding

tokenisation_service = TokenisationService()
