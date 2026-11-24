from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from decimal import Decimal
from dvp_v2_client import NovaDvPV2Client
from dotenv import load_dotenv

# Ensure env variables are loaded
load_dotenv()

router = APIRouter(prefix="/api/v1/settlement-v2", tags=["Atomic Settlement V2"])

# Initialize the client
client = NovaDvPV2Client()

class SettlementRequest(BaseModel):
    order_id: str
    buyer: str
    seller: str
    dkhyr_amount: float
    share_amount: float

@router.post("/settle-atomic")
async def settle_atomic(req: SettlementRequest):
    try:
        # Convert float amounts to 18-decimal Wei
        dkhyr_wei = int(Decimal(str(req.dkhyr_amount)) * Decimal(10**18))
        share_wei = int(Decimal(str(req.share_amount)) * Decimal(10**18))

        # 1. Pre-check (Dry Run)
        preview = client.preview(
            req.order_id, req.buyer, req.seller, dkhyr_wei, share_wei
        )
        
        if not preview["ok"]:
            # This will now correctly return a 400, not a 500
            raise HTTPException(
                status_code=400, 
                detail=f"Preview failed: {preview['reason']}"
            )

        # 2. Execute Atomic Settlement
        receipt = client.settle(
            req.order_id, req.buyer, req.seller, dkhyr_wei, share_wei
        )
        
        if receipt.get("status") != 1:
            raise HTTPException(status_code=500, detail="Transaction reverted on-chain.")

        return {
            "status": "success",
            "message": "Atomic DvP Settled on Base Mainnet",
            "tx_hash": receipt["tx_hash"],
            "settlement_id": receipt.get("settlement_id"),
            "block_number": receipt["block_number"]
        }

    except HTTPException as http_exc:
        # Re-raise HTTPExceptions so FastAPI handles the status code correctly
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
