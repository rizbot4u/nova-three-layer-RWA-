import os
import sys
import asyncio
import logging
from web3 import Web3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [NOVA-SENTINEL] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("nova.sentinel")

RPC_URL = os.getenv("BASE_MAINNET_RPC", "https://mainnet.base.org")
CHECK_INTERVAL_SECONDS = int(os.getenv("SENTINEL_POLL_INTERVAL", "30"))


async def run_cycle(w3):
    from app.database import AsyncSessionLocal
    from app.sentinel.auditor import SentinelAuditor

    async with AsyncSessionLocal() as db:
        auditor = SentinelAuditor(w3, db)
        await auditor.audit_settled_orders()


async def main():
    logger.info("🛡️  Starting Layer 4: nova-sentinel Audit Daemon...")
    w3 = Web3(Web3.HTTPProvider(RPC_URL))

    if not w3.is_connected():
        logger.error(f"Cannot connect to Base Mainnet RPC at {RPC_URL}")
        sys.exit(1)

    logger.info(f"Connected to Base Mainnet | Chain ID: {w3.eth.chain_id}")

    while True:
        try:
            if not w3.is_connected():
                logger.warning("RPC disconnected. Reconnecting...")
                w3 = Web3(Web3.HTTPProvider(RPC_URL))
            await run_cycle(w3)
        except Exception as e:
            logger.error(f"Sentinel loop error: {e}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
