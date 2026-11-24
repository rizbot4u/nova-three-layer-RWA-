from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

class ShareIssue(BaseModel):
    property_id: UUID
    investor_id: UUID
    amount: int

class ShareHoldingOut(BaseModel):
    id: UUID
    property_id: UUID
    investor_id: UUID
    shares: int
    last_updated: datetime
    class Config:
        from_attributes = True
