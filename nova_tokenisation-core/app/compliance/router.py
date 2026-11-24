from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.compliance.models import KYCWhitelist
from web3 import Web3

router = APIRouter(prefix="/api/v1/compliance", tags=["Compliance"])

# Connect to Base Mainnet
w3 = Web3(Web3.HTTPProvider("https://base-mainnet.g.alchemy.com/v2/2mcrNfMkBxuSbN3D77b77pyfjFAv1k7Z"))
CONTRACT_ADDRESS = Web3.to_checksum_address("0x11b229E0F4a0DAee8B8Bf20BdED941b7ba4E8C4c")

# Minimal ABI to check whitelist
ABI = [{"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"whitelist","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}]
contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=ABI)

class WhitelistRequest(BaseModel):
    wallet_address: str
    is_whitelisted: bool
    jurisdiction: str = "EU"
    lockup_until: int | None = None

@router.post("/whitelist")
async def update_whitelist(payload: WhitelistRequest, db: AsyncSession = Depends(get_db)):
    wallet = payload.wallet_address.lower()
    result = await db.execute(select(KYCWhitelist).where(KYCWhitelist.wallet_address == wallet))
    record = result.scalars().first()

    if not record:
        record = KYCWhitelist(
            wallet_address=wallet,
            is_whitelisted=payload.is_whitelisted,
            jurisdiction=payload.jurisdiction,
            lockup_until=payload.lockup_until,
        )
        db.add(record)
    else:
        record.is_whitelisted = payload.is_whitelisted
        record.jurisdiction = payload.jurisdiction
        if payload.lockup_until is not None:
            record.lockup_until = payload.lockup_until

    await db.commit()
    return {"status": "success", "wallet": wallet, "is_whitelisted": payload.is_whitelisted}

@router.get("/whitelist/{wallet_address}")
async def check_whitelist(wallet_address: str, db: AsyncSession = Depends(get_db)):
    wallet = wallet_address.strip().lower() # Strip whitespace!
    
    # 1. Check the actual blockchain
    try:
        checksum_wallet = Web3.to_checksum_address(wallet)
        is_onchain_whitelisted = contract.functions.whitelist(checksum_wallet).call()
    except Exception as e:
        print(f"Blockchain read error: {e}")
        is_onchain_whitelisted = False

    # 2. Check the database
    result = await db.execute(select(KYCWhitelist).where(KYCWhitelist.wallet_address == wallet))
    record = result.scalars().first()

    # Return true if either on-chain OR in database says true
    final_status = is_onchain_whitelisted or (record and record.is_whitelisted)

    if not final_status:
        return {"wallet": wallet, "whitelisted": False}
        
    return {
        "wallet": wallet,
        "whitelisted": True,
        "jurisdiction": record.jurisdiction if record else "Unknown",
        "lockup_until": record.lockup_until if record else 0,
    }
