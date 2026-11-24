from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr

class InvestorCreate(BaseModel):
    email: EmailStr
    full_name: str
    country: str

class InvestorOut(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    country: str
    kyc_status: str
    investor_category: str
    aml_risk_score: int
    created_at: datetime
    class Config:
        from_attributes = True
