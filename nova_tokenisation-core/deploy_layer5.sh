#!/bin/bash
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_DIR="$(pwd)"

echo "=================================================="
echo "🚀 DEPLOYING LAYER 5: PERMISSIONED SECONDARY MARKET"
echo "=================================================="

# ---------- 0. Pre-flight ----------
echo "🔍 Pre-flight..."
DF_FREE=$(df --output=avail /var/lib/docker | tail -1 | tr -d ' ')
echo "   Disk free: ${DF_FREE} KB"
if [ "$DF_FREE" -lt 3000000 ]; then
    echo "   ⚠️  Low disk (<3GB). Running vfs-safe prune..."
    docker image prune -f
    docker builder prune -f 2>/dev/null || true
fi

# ---------- 1. Directories ----------
mkdir -p app/compliance
mkdir -p contracts/scripts
echo "📁 Directories ready."

# ---------- 2. Compliance package init ----------
cat << 'EOF' > app/compliance/__init__.py
# Layer 5 — Compliance & KYC Whitelist
EOF

# ---------- 3. SQLAlchemy models ----------
cat << 'EOF' > app/compliance/models.py
from sqlalchemy import Column, String, Boolean, DateTime, BigInteger
from datetime import datetime, timezone
from app.database import Base


class KYCWhitelist(Base):
    __tablename__ = "kyc_whitelists"

    wallet_address = Column(String(42), primary_key=True, index=True)
    is_whitelisted = Column(Boolean, default=False, nullable=False)
    jurisdiction = Column(String(8), nullable=True)
    kyc_provider = Column(String(64), nullable=True)
    lockup_until = Column(BigInteger, nullable=True)
    updated_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class WhitelistSyncLog(Base):
    __tablename__ = "whitelist_sync_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    wallet_address = Column(String(42), nullable=False)
    action = Column(String(16), nullable=False)
    tx_hash = Column(String(66), nullable=True)
    status = Column(String(16), nullable=False)
    error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc))
EOF
echo "📝 app/compliance/models.py"

# ---------- 4. Compliance router ----------
cat << 'EOF' > app/compliance/router.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.compliance.models import KYCWhitelist

router = APIRouter(prefix="/api/v1/compliance", tags=["Compliance"])


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
    wallet = wallet_address.lower()
    result = await db.execute(select(KYCWhitelist).where(KYCWhitelist.wallet_address == wallet))
    record = result.scalars().first()
    if not record or not record.is_whitelisted:
        return {"wallet": wallet, "whitelisted": False}
    return {
        "wallet": wallet,
        "whitelisted": True,
        "jurisdiction": record.jurisdiction,
        "lockup_until": record.lockup_until,
    }
EOF
echo "📝 app/compliance/router.py"

# ---------- 5. Inject router into app/main.py safely ----------
python3 << 'PYEOF'
path = "app/main.py"
with open(path) as f:
    src = f.read()

IMPORT_LINE = "from app.compliance.router import router as compliance_router"
INCLUDE_LINE = "app.include_router(compliance_router)"

if IMPORT_LINE not in src:
    lines = src.split("\n")
    last_import = -1
    for i, l in enumerate(lines):
        if l.startswith("from app.") or l.startswith("import app."):
            last_import = i
    if last_import >= 0:
        lines.insert(last_import + 1, IMPORT_LINE)
    else:
        lines.insert(0, IMPORT_LINE)
    src = "\n".join(lines)
    print("   ✅ Import injected.")

if INCLUDE_LINE not in src:
    lines = src.split("\n")
    for i, l in enumerate(lines):
        if "app = FastAPI(" in l:
            j = i
            while j < len(lines) and not lines[j].rstrip().endswith(")"):
                j += 1
            lines.insert(j + 1, "")
            lines.insert(j + 2, INCLUDE_LINE)
            break
    src = "\n".join(lines)
    print("   ✅ include_router injected.")

with open(path, "w") as f:
    f.write(src)
PYEOF

# ---------- 6. Solidity contract ----------
cat << 'EOF' > contracts/PermissionedNVP.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PermissionedNVP is ERC20, Ownable {
    mapping(address => bool) public whitelisted;
    mapping(address => uint256) public lockupUntil;

    address public treasury;

    event WhitelistUpdated(address indexed wallet, bool allowed);
    event LockupUpdated(address indexed wallet, uint256 until);
    event TransferBlocked(address indexed from, address indexed to, string reason);

    constructor(
        string memory name_,
        string memory symbol_,
        address treasury_,
        address initialOwner
    ) ERC20(name_, symbol_) Ownable(initialOwner) {
        treasury = treasury_;
        whitelisted[treasury_] = true;
    }

    function setTreasury(address t) external onlyOwner {
        treasury = t;
        whitelisted[t] = true;
    }

    function setWhitelisted(address wallet, bool allowed) external onlyOwner {
        whitelisted[wallet] = allowed;
        emit WhitelistUpdated(wallet, allowed);
    }

    function setWhitelistedBatch(address[] calldata wallets, bool allowed) external onlyOwner {
        for (uint256 i = 0; i < wallets.length; i++) {
            whitelisted[wallets[i]] = allowed;
            emit WhitelistUpdated(wallets[i], allowed);
        }
    }

    function setLockup(address wallet, uint256 until) external onlyOwner {
        lockupUntil[wallet] = until;
        emit LockupUpdated(wallet, until);
    }

    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }

    function burn(address from, uint256 amount) external onlyOwner {
        _burn(from, amount);
    }

    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0)) {
            if (!whitelisted[from]) {
                emit TransferBlocked(from, to, "sender_not_whitelisted");
                revert("PermissionedNVP: sender not whitelisted");
            }
            if (lockupUntil[from] > 0 && block.timestamp < lockupUntil[from]) {
                emit TransferBlocked(from, to, "sender_locked_up");
                revert("PermissionedNVP: sender locked up");
            }
        }
        if (to != address(0) && to != treasury) {
            if (!whitelisted[to]) {
                emit TransferBlocked(from, to, "receiver_not_whitelisted");
                revert("PermissionedNVP: receiver not whitelisted");
            }
        }
        super._update(from, to, value);
    }
}
EOF
echo "📝 contracts/PermissionedNVP.sol"

# ---------- 7. Hardhat deploy script ----------
cat << 'EOF' > contracts/scripts/deploy_permissioned.js
const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying PermissionedNVP from:", deployer.address);

  const Treasury = process.env.TREASURY_WALLET_ADDRESS;
  if (!Treasury) throw new Error("TREASURY_WALLET_ADDRESS env not set");

  const Factory = await hre.ethers.getContractFactory("PermissionedNVP");
  const token = await Factory.deploy(
    "Permissioned NVP",
    "NVP-2",
    Treasury,
    deployer.address
  );
  await token.waitForDeployment();

  const addr = await token.getAddress();
  console.log("PermissionedNVP deployed at:", addr);
  console.log("Explorer:", `https://basescan.org/address/${addr}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
EOF
echo "📝 contracts/scripts/deploy_permissioned.js"

# ---------- 8. Postgres schema (raw SQL — never trust Alembic on vfs) ----------
echo "📦 Bringing up postgres..."
docker compose up -d postgres

echo "⏳ Waiting for postgres..."
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U nova >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

docker compose exec -T postgres psql -U nova -d nova_tokenisation <<'SQL'
CREATE TABLE IF NOT EXISTS kyc_whitelists (
    wallet_address VARCHAR(42) PRIMARY KEY,
    is_whitelisted BOOLEAN NOT NULL DEFAULT FALSE,
    jurisdiction VARCHAR(8),
    kyc_provider VARCHAR(64),
    lockup_until BIGINT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS whitelist_sync_log (
    id BIGSERIAL PRIMARY KEY,
    wallet_address VARCHAR(42) NOT NULL,
    action VARCHAR(16) NOT NULL,
    tx_hash VARCHAR(66),
    status VARCHAR(16) NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
SQL
echo "   ✅ Postgres schema ready."

# ---------- 9. Build API + Sentinel sequentially ----------
echo "🏗️  Building api..."
docker compose build api

echo "🏗️  Building nova-sentinel..."
docker compose build nova-sentinel

echo "🚀 Starting stack..."
docker compose up -d

sleep 8
docker compose ps

# ---------- 10. Compile + deploy contract ----------
if [ -f contracts/hardhat.config.js ] || [ -f contracts/hardhat.config.ts ]; then
    echo "📦 Compiling PermissionedNVP.sol..."
    (cd contracts && npx hardhat compile) || echo "   ⚠️  Hardhat compile returned non-zero — check output above."
else
    echo "   ℹ️  No hardhat.config in contracts/ — skipping compile."
    echo "   ℹ️  Your existing Hardhat env is likely at the repo root."
    echo "   ℹ️  To deploy: npx hardhat run contracts/scripts/deploy_permissioned.js --network base"
fi

# ---------- 11. Verify endpoint ----------
echo ""
echo "=================================================="
echo "✅ LAYER 5 DEPLOYED"
echo "=================================================="
echo "🔍 Verifying compliance endpoint..."
sleep 2
curl -sS "http://127.0.0.1:8100/api/v1/compliance/whitelist/0x66e9a79aDb97Bae948E97c09F1eE555f6E4c6767" | python3 -m json.tool 2>/dev/null || echo "   ⚠️  API not yet ready — check logs below"

echo ""
echo "📜 Live logs (Ctrl+C to exit):"
docker compose logs -f --tail=20 api
