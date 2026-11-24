import os
import logging
from decimal import Decimal
from web3 import Web3
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, or_, and_

logger = logging.getLogger("nova.sentinel")

TRANSFER_EVENT_SIG = Web3.keccak(text="Transfer(address,address,uint256)").hex()
MIN_CONFIRMATIONS = int(os.getenv("SENTINEL_MIN_CONFIRMATIONS", "3"))
RE_AUDIT_HOURS = int(os.getenv("SENTINEL_RE_AUDIT_HOURS", "24"))


class SentinelAuditor:
    def __init__(self, w3: Web3, db):
        self.w3 = w3
        self.db = db

    async def audit_settled_orders(self):
        from app.models.escrow import EscrowOrder

        cutoff = datetime.now(timezone.utc) - timedelta(hours=RE_AUDIT_HOURS)

        result = await self.db.execute(
            select(EscrowOrder).where(
                EscrowOrder.state == "settled",
                or_(
                    EscrowOrder.audit_status != "VERIFIED",
                    EscrowOrder.audit_status.is_(None),
                    and_(
                        EscrowOrder.last_audited_at.isnot(None),
                        EscrowOrder.last_audited_at < cutoff,
                    ),
                ),
            )
        )
        orders = result.scalars().all()

        if not orders:
            logger.info("No SETTLED orders pending audit.")
            return

        for order in orders:
            await self._audit_one(order)

    async def _audit_one(self, order):
        tx_hash = order.settlement_tx_hash
        if not tx_hash:
            logger.error(f"❌ Order {order.id} SETTLED but missing tx_hash")
            order.audit_status = "FAILED"
            await self.db.commit()
            return

        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        except Exception as e:
            logger.warning(f"⏳ RPC retry pending | Order {order.id} | {e}")
            return

        if not receipt or receipt.get("status") != 1:
            logger.critical(f"🚨 TX FAILED on-chain | Order: {order.id}")
            order.audit_status = "FAILED"
            await self.db.commit()
            return

        confirmations = self.w3.eth.block_number - receipt.get("blockNumber", 0)
        if confirmations < MIN_CONFIRMATIONS:
            logger.warning(f"⏳ PENDING FINALITY | Order: {order.id} | {confirmations}/{MIN_CONFIRMATIONS}")
            return

        expected_recipient = order.investor_wallet.lower()
        expected_nvp1 = int(order.share_amount * (10 ** 18))

        total_dkhyr_dec = Decimal(str(order.total_dkhyr)) if order.total_dkhyr else Decimal("0")
        expected_dkhyr = int(total_dkhyr_dec * Decimal(10 ** 18))

        asset_contract = (order.asset_contract or "").lower() or None
        currency_contract = (order.currency_contract or "").lower() or None

        matched_amount = None
        matched_token = None
        matched_from = None

        for log in receipt.get("logs", []):
            topics = log.get("topics", [])
            if len(topics) < 3:
                continue
            if topics[0].hex() != TRANSFER_EVENT_SIG:
                continue

            token_addr = log["address"].lower()

            # Skip logs that don't belong to either tracked token
            if asset_contract and currency_contract:
                if token_addr not in (asset_contract, currency_contract):
                    continue
            elif asset_contract and token_addr != asset_contract:
                continue
            elif currency_contract and token_addr != currency_contract:
                continue

            from_addr = "0x" + topics[1].hex()[-40:]
            to_addr = "0x" + topics[2].hex()[-40:]
            amount = int(log["data"].hex(), 16)

            if to_addr.lower() != expected_recipient:
                continue

            if asset_contract and token_addr == asset_contract and amount == expected_nvp1:
                matched_amount = amount
                matched_token = "NVP-1"
                matched_from = from_addr
                break
            if currency_contract and token_addr == currency_contract and amount == expected_dkhyr:
                matched_amount = amount
                matched_token = "DKHYR"
                matched_from = from_addr
                break

        if matched_amount is None:
            logger.critical(
                f"🚨 EVENT MISMATCH | Order: {order.id} | "
                f"Expected {expected_nvp1} NVP-1 or {expected_dkhyr} DKHYR to {expected_recipient[:10]}"
            )
            order.audit_status = "FAILED"
            await self.db.commit()
            return

        order.audit_status = "VERIFIED"
        order.last_audited_at = datetime.now(timezone.utc)
        await self.db.commit()
        logger.info(
            f"✅ AUDIT VERIFIED | Order: {order.id} | Token: {matched_token} | "
            f"From: {matched_from[:10]}... | To: {expected_recipient[:10]}... | "
            f"Tx: {tx_hash[:10]}... | Block: {receipt.get('blockNumber')} | "
            f"Confirmations: {confirmations} | Amount: {matched_amount}"
        )
