from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.escrow import EscrowEvent, EscrowOrder
from app.schemas.escrow import (
    EscrowActionResponse,
    EscrowCreateRequest,
    EscrowDetail,
)
from app.services.deposit_verifier import deposit_verifier
from app.services.settlement_service import settlement_service

router = APIRouter(prefix="/api/v1/escrow", tags=["Layer 3: Payments & Escrow"])


async def _log(db: AsyncSession, order_id, event_type: str, payload: dict | None = None):
    ev = EscrowEvent(order_id=order_id, event_type=event_type, payload=payload or {})
    db.add(ev)
    await db.commit()


def _to_detail(o: EscrowOrder) -> EscrowDetail:
    return EscrowDetail(
        order_id=o.id,
        direction=o.direction,
        investor_wallet=o.investor_wallet,
        asset_contract=o.asset_contract,
        currency_contract=o.currency_contract,
        share_amount=o.share_amount,
        price_dkhyr=float(o.price_dkhyr),
        total_dkhyr=float(o.total_dkhyr),
        state=o.state,
        deposit_tx_hash=o.deposit_tx_hash,
        settlement_tx_hash=o.settlement_tx_hash,
        created_at=o.created_at,
        updated_at=o.updated_at,
    )


@router.post("/create", response_model=EscrowActionResponse, status_code=status.HTTP_201_CREATED)
async def create_escrow_order(payload: EscrowCreateRequest, db: AsyncSession = Depends(get_db)):
    if payload.direction not in ("buy", "sell"):
        raise HTTPException(400, "direction must be 'buy' or 'sell'")

    total_dkhyr = payload.share_amount * payload.price_dkhyr

    order = EscrowOrder(
        direction=payload.direction,
        investor_wallet=payload.investor_wallet,
        asset_contract=payload.asset_contract,
        currency_contract=payload.currency_contract,
        share_amount=payload.share_amount,
        price_dkhyr=payload.price_dkhyr,
        total_dkhyr=total_dkhyr,
        state="pending",
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    await _log(db, order.id, "ORDER_CREATED", {
        "direction": payload.direction,
        "shares": payload.share_amount,
        "price_dkhyr": payload.price_dkhyr,
        "total_dkhyr": float(total_dkhyr),
        "asset_contract": payload.asset_contract,
        "currency_contract": payload.currency_contract,
    })

    return EscrowActionResponse(
        order_id=order.id,
        state=order.state,
        message=f"{payload.direction.upper()} order created.",
        updated_at=order.updated_at,
    )


@router.post("/{order_id}/fund", response_model=EscrowActionResponse)
async def fund_escrow_order(
    order_id: UUID,
    deposit_tx_hash: str,
    db: AsyncSession = Depends(get_db),
):
    order = (await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Escrow order not found")
    if order.state != "pending":
        raise HTTPException(400, f"Cannot fund order in state '{order.state}'")

    if order.direction == "buy":
        # Investor must have sent DKHYR to the treasury
        expected_from = order.investor_wallet
        expected_to = settlement_service.treasury
        expected_amount = float(order.total_dkhyr)
        token_to_check = order.currency_contract
    else:
        # Sell: investor must have sent NVP-1 to the treasury
        expected_from = order.investor_wallet
        expected_to = settlement_service.treasury
        expected_amount = float(order.share_amount)
        token_to_check = order.asset_contract

    ok, reason = deposit_verifier.verify_transfer(
        tx_hash=deposit_tx_hash,
        token_contract=token_to_check,
        expected_from=expected_from,
        expected_to=expected_to,
        expected_amount_whole=expected_amount,
    )

    if not ok:
        await _log(db, order.id, "ORDER_FUND_VERIFICATION_FAILED", {
            "reason": reason, "tx_hash": deposit_tx_hash,
        })
        raise HTTPException(400, f"Deposit verification failed: {reason}")

    order.state = "funded"
    order.deposit_tx_hash = deposit_tx_hash
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Log in a fresh session — the request-scoped session is poisoned
        # after the failed flush and will re-raise on any further write.
        try:
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as fresh_db:
                await _log(fresh_db, order.id, "ORDER_FUND_REPLAY_REJECTED", {
                    "tx_hash": deposit_tx_hash,
                })
        except Exception:
            pass  # audit is best-effort on the error path
        raise HTTPException(
            409,
            f"Deposit tx {deposit_tx_hash} has already been used to fund another order",
        )
    await db.refresh(order)

    await _log(db, order.id, "ORDER_FUNDED", {
        "tx_hash": deposit_tx_hash,
        "token": token_to_check,
        "amount": expected_amount,
    })

    return EscrowActionResponse(
        order_id=order.id,
        state=order.state,
        message="Deposit verified. Escrow funded.",
        updated_at=order.updated_at,
    )


@router.post("/{order_id}/settle", response_model=EscrowActionResponse)
async def settle_escrow_order(order_id: UUID, db: AsyncSession = Depends(get_db)):
    order = (await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Escrow order not found")
    if order.state != "funded":
        raise HTTPException(400, f"Order must be 'funded' to settle (currently '{order.state}')")

    try:
        if order.direction == "buy":
            # Investor paid DKHYR, receives NVP-1
            tx_hash = settlement_service.send_token(
                token_contract=order.asset_contract,
                to_wallet=order.investor_wallet,
                amount_whole_tokens=float(order.share_amount),
            )
        else:
            # Sell: investor paid NVP-1, receives DKHYR
            tx_hash = settlement_service.send_token(
                token_contract=order.currency_contract,
                to_wallet=order.investor_wallet,
                amount_whole_tokens=float(order.total_dkhyr),
            )
    except Exception as e:
        await _log(db, order.id, "ORDER_SETTLE_FAILED", {"error": str(e)})
        raise HTTPException(500, f"Settlement failed: {e}")

    order.state = "settled"
    order.settlement_tx_hash = tx_hash
    await db.commit()
    await db.refresh(order)

    await _log(db, order.id, "ORDER_SETTLED", {
        "tx_hash": tx_hash,
        "direction": order.direction,
        "to": order.investor_wallet,
    })

    return EscrowActionResponse(
        order_id=order.id,
        state=order.state,
        message=f"{order.direction.upper()} settled on Base Mainnet.",
        settlement_tx_hash=tx_hash,
        updated_at=order.updated_at,
    )


@router.post("/{order_id}/cancel", response_model=EscrowActionResponse)
async def cancel_escrow_order(order_id: UUID, db: AsyncSession = Depends(get_db)):
    order = (await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Escrow order not found")
    if order.state not in ("pending", "funded"):
        raise HTTPException(400, f"Cannot cancel order in state '{order.state}'")

    order.state = "cancelled"
    await db.commit()
    await db.refresh(order)
    await _log(db, order.id, "ORDER_CANCELLED", {})

    return EscrowActionResponse(
        order_id=order.id,
        state=order.state,
        message="Escrow cancelled.",
        updated_at=order.updated_at,
    )



from pydantic import BaseModel

class DemoAirdropRequest(BaseModel):
    wallet_address: str
    amount_dkhyr: float = 10000.0

@router.post("/demo-airdrop")
async def demo_airdrop(payload: DemoAirdropRequest):
    try:
        tx_hash = settlement_service.send_token(
            token_contract="0x9991bE994829601F90328CCF9cee4D1A55ADae70",
            to_wallet=payload.wallet_address.strip(),
            amount_whole_tokens=float(payload.amount_dkhyr),
        )
        return {
            "status": "sent",
            "wallet": payload.wallet_address.strip(),
            "amount_dkhyr": payload.amount_dkhyr,
            "tx_hash": tx_hash,
        }
    except Exception as e:
        raise HTTPException(500, f"Airdrop transfer failed: {e}")

@router.get("/{order_id}", response_model=EscrowDetail)
async def get_escrow_order(order_id: UUID, db: AsyncSession = Depends(get_db)):
    order = (await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Escrow order not found")
    return _to_detail(order)


@router.get("/", response_model=list[EscrowDetail])
async def list_escrow_orders(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EscrowOrder).order_by(EscrowOrder.created_at.desc()).limit(100)
    )
    return [_to_detail(o) for o in result.scalars().all()]
