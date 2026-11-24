from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EscrowCreateRequest(BaseModel):
    direction: str = Field("buy", description="'buy' = pay DKHYR, receive NVP-1; 'sell' = pay NVP-1, receive DKHYR")
    investor_wallet: str = Field(..., description="Investor EVM address (0x...)")
    asset_contract: str = Field(..., description="NovaPropertyShare contract (NVP-1)")
    currency_contract: str = Field(..., description="DKHYR ERC-20 contract")
    share_amount: int = Field(..., gt=0, description="Whole-token shares")
    price_dkhyr: float = Field(..., gt=0, description="DKHYR per whole share")


class EscrowActionResponse(BaseModel):
    order_id: UUID
    state: str
    message: str
    settlement_tx_hash: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class EscrowDetail(BaseModel):
    order_id: UUID
    direction: str
    investor_wallet: str
    asset_contract: str
    currency_contract: str
    share_amount: int
    price_dkhyr: float
    total_dkhyr: float
    state: str
    deposit_tx_hash: Optional[str] = None
    settlement_tx_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
