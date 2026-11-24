from fastapi import APIRouter
from pydantic import BaseModel
import httpx
import os

router = APIRouter(prefix="/api/v1", tags=["Listener"])

WATCHED_CONTRACTS = []

class WatchRequest(BaseModel):
    chain: str
    address: str

class EventPayload(BaseModel):
    chain: str
    txHash: str
    tokenAddress: str
    sender: str
    amountUsd: float
    tokenSymbol: str

@router.get("/watchlist")
async def get_watchlist():
    return {"contracts": WATCHED_CONTRACTS}

@router.post("/watchlist")
async def add_to_watchlist(req: WatchRequest):
    WATCHED_CONTRACTS.append({"chain": req.chain, "address": req.address})
    return {"status": "added", "contracts": WATCHED_CONTRACTS}

@router.post("/event")
async def receive_event(event: EventPayload):
    print(f"🚨 ALERT RECEIVED: {event.amountUsd} {event.tokenSymbol} on {event.chain}. Tx: {event.txHash}")
    
    # Send to Telegram Bot (Optional: replace with your Telegram ID or group ID)
    # If you don't have a specific chat ID, you can use the bot to message you directly.
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6517213957") # Put your Telegram ID here

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID != "6517213957":
        message = (
            f"🚨 *NOVA ALERT*\n\n"
            f"Chain: {event.chain.upper()}\n"
            f"Token: {event.tokenSymbol}\n"
            f"Amount: {event.amountUsd}\n"
            f"Sender: `{event.sender}`\n"
            f"Tx: `{event.txHash}`"
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown"
                })
            except Exception as e:
                print(f"Failed to send Telegram alert: {e}")

    return {"status": "received"}
