from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

class PropertyCreate(BaseModel):
    address: str
    postcode: str
    valuation_gbp: float
    total_supply: int = 500_000_000

class PropertyOut(BaseModel):
    id: UUID
    address: str
    postcode: str
    valuation_gbp: float
    total_supply: int
    circulating_supply: int
    status: str
    created_at: datetime
    class Config:
        from_attributes = True
