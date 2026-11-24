#!/bin/bash
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_DIR="$(pwd)"

echo "=================================================="
echo "🛡️  DEPLOYING LAYER 4: NOVA-SENTINEL (v6)"
echo "=================================================="

# ---------- 1. Sentinel files ----------
mkdir -p app/sentinel

cat << 'EOF' > app/sentinel/__init__.py
# Nova Sentinel (Layer 4)
EOF

cat << 'EOF' > app/sentinel/auditor.py
import os
import logging
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
        expected_dkhyr = int(float(order.total_dkhyr) * (10 ** 18))
        expected_token = order.currency_contract.lower() if order.currency_contract else None

        matched_amount = None
        for log in receipt.get("logs", []):
            topics = log.get("topics", [])
            if len(topics) < 3:
                continue
            if topics[0].hex() != TRANSFER_EVENT_SIG:
                continue
            if expected_token and log["address"].lower() != expected_token:
                continue

            to_addr = "0x" + topics[2].hex()[-40:]
            amount = int(log["data"].hex(), 16)

            if to_addr.lower() != expected_recipient:
                continue
            if amount in (expected_nvp1, expected_dkhyr):
                matched_amount = amount
                break

        if matched_amount is None:
            logger.critical(
                f"🚨 EVENT MISMATCH | Order: {order.id} | "
                f"Expected {expected_nvp1} or {expected_dkhyr} to {expected_recipient[:10]}"
            )
            order.audit_status = "FAILED"
            await self.db.commit()
            return

        order.audit_status = "VERIFIED"
        order.last_audited_at = datetime.now(timezone.utc)
        await self.db.commit()
        logger.info(
            f"✅ AUDIT VERIFIED | Order: {order.id} | "
            f"Tx: {tx_hash[:10]}... | Block: {receipt.get('blockNumber')} | "
            f"Confirmations: {confirmations} | Amount: {matched_amount}"
        )
EOF

cat << 'EOF' > app/sentinel/daemon.py
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
EOF

echo "📝 Sentinel files written."

# ---------- 2. Patch escrow.py ----------
python3 << 'PYEOF'
import re, sys
path = "app/models/escrow.py"
with open(path) as f:
    src = f.read()
if "audit_status" in src:
    print("   ℹ️  audit_status already present.")
    sys.exit(0)
anchor_re = re.compile(
    r"^(\s*id\s*=\s*Column\(UUID\(as_uuid=True\),\s*primary_key=True,\s*default=uuid\.uuid4\)\s*)$",
    re.MULTILINE,
)
new_fields = (
    "    audit_status = Column(String(16), nullable=True, default=\"PENDING\")\n"
    "    last_audited_at = Column(DateTime(timezone=True), nullable=True)\n"
)
if not anchor_re.search(src):
    print("   ⚠️  Anchor not found. Aborting.")
    sys.exit(1)
src_new = anchor_re.sub(lambda m: m.group(0) + "\n" + new_fields.rstrip("\n"), src, count=1)
with open(path, "w") as f:
    f.write(src_new)
print("   ✅ escrow.py patched.")
PYEOF

# ---------- 3. Patch migrations/env.py ----------
python3 << 'PYEOF'
import sys
path = "migrations/env.py"
with open(path) as f:
    src = f.read()
marker = "# --- NOVA SENTINEL: ensure project root on sys.path ---"
if marker in src:
    print("   ℹ️  env.py already patched.")
    sys.exit(0)
patch = (
    f"{marker}\n"
    "import sys, os\n"
    "sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))\n"
    "# --- end NOVA SENTINEL patch ---\n\n"
)
lines = src.split("\n")
out = []
inserted = False
for line in lines:
    if not inserted and line.strip().startswith(("import ", "from ")):
        out.append(patch.rstrip("\n"))
        inserted = True
    out.append(line)
with open(path, "w") as f:
    f.write("\n".join(out))
print("   ✅ env.py patched.")
PYEOF

# ---------- 4. .env ----------
touch .env
grep -q "SENTINEL_MIN_CONFIRMATIONS" .env || echo "SENTINEL_MIN_CONFIRMATIONS=3" >> .env
grep -q "SENTINEL_POLL_INTERVAL"      .env || echo "SENTINEL_POLL_INTERVAL=30" >> .env
grep -q "SENTINEL_RE_AUDIT_HOURS"     .env || echo "SENTINEL_RE_AUDIT_HOURS=24" >> .env
grep -q "BASE_MAINNET_RPC"            .env || echo "BASE_MAINNET_RPC=https://mainnet.base.org" >> .env

# ---------- 5. Rebuild docker-compose.yml (add nova-sentinel) ----------
if ! grep -q "^  nova-sentinel:" docker-compose.yml; then
    cp docker-compose.yml "docker-compose.yml.bak.$(date +%s)"
    python3 << 'PYEOF'
with open("docker-compose.yml") as f:
    src = f.read()

# Insert nova-sentinel just before the top-level "volumes:" key
block = """
  nova-sentinel:
    build: .
    container_name: nova-sentinel
    command: python3 -m app.sentinel.daemon
    working_dir: /app
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+asyncpg://nova:nova_dev_password@postgres:5432/nova_tokenisation
      REDIS_URL: redis://redis:6379/0
      BASE_MAINNET_RPC: ${BASE_MAINNET_RPC:-https://mainnet.base.org}
      SENTINEL_MIN_CONFIRMATIONS: ${SENTINEL_MIN_CONFIRMATIONS:-3}
      SENTINEL_POLL_INTERVAL: ${SENTINEL_POLL_INTERVAL:-30}
      SENTINEL_RE_AUDIT_HOURS: ${SENTINEL_RE_AUDIT_HOURS:-24}
    volumes: [".:/app"]
    restart: unless-stopped
"""

lines = src.split("\n")
out = []
inserted = False
for line in lines:
    if not inserted and line.startswith("volumes:"):
        out.append(block.rstrip("\n"))
        inserted = True
    out.append(line)
with open("docker-compose.yml", "w") as f:
    f.write("\n".join(out))
print("   ✅ nova-sentinel service added to docker-compose.yml.")
PYEOF
else
    echo "   ℹ️  nova-sentinel already in docker-compose.yml."
fi

# ---------- 6. Validate ----------
docker compose config --quiet && echo "   ✅ YAML valid."

# ---------- 7. Force-recreate api so patched env.py is live ----------
echo "🔄 Force-recreating api container..."
docker compose up -d --force-recreate postgres redis
docker compose up -d --force-recreate api
sleep 4

# ---------- 8. Alembic ----------
echo "📦 Alembic autogenerate..."
docker compose exec -T -e PYTHONPATH=/app api alembic revision --autogenerate -m "add sentinel audit fields" || true

echo "🔍 Checking if a new migration was written..."
NEW_MIG=$(ls -t migrations/versions/*.py 2>/dev/null | head -1 || true)
if [ -z "$NEW_MIG" ] || ! grep -q "audit_status" "$NEW_MIG"; then
    echo "   ⚠️  Autogenerate didn't emit audit_status. Writing migration manually..."

    TS=$(date +%Y%m%d%H%M%S)
    MIGFILE="migrations/versions/${TS}_add_sentinel_audit_fields.py"

    cat > "$MIGFILE" <<'PYMIG'
"""add sentinel audit fields

Revision ID: sentinel_audit_001
Revises: 
Create Date: auto-generated by nova deploy_layer4.sh
"""
from alembic import op
import sqlalchemy as sa

revision = "sentinel_audit_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("escrow_orders", sa.Column("audit_status", sa.String(length=16), nullable=True))
    op.add_column("escrow_orders", sa.Column("last_audited_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("escrow_orders", "last_audited_at")
    op.drop_column("escrow_orders", "audit_status")
PYMIG

    echo "   ✅ Manual migration written: $MIGFILE"
fi

echo "🚀 Applying migration..."
docker compose exec -T -e PYTHONPATH=/app api alembic upgrade head

# ---------- 9. Verify column exists ----------
echo "🔍 Verifying column in Postgres..."
docker compose exec -T postgres psql -U nova -d nova_tokenisation -c \
    "SELECT column_name FROM information_schema.columns WHERE table_name='escrow_orders' AND column_name IN ('audit_status','last_audited_at');"

# ---------- 10. Build & run sentinel ----------
echo "🏗️  Building nova-sentinel image..."
docker compose build nova-sentinel

echo "🚀 Starting nova-sentinel..."
docker compose up -d --force-recreate nova-sentinel

echo ""
echo "=================================================="
echo "✅ LAYER 4 DEPLOYED"
echo "=================================================="
docker compose ps nova-sentinel
echo ""
echo "📜 Live logs (Ctrl+C to exit log view)..."
docker compose logs -f --tail=30 nova-sentinel
