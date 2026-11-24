#!/bin/bash
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_DIR="$(pwd)"

echo "=================================================="
echo "🧊 FREEZING NOVA TOKENISATION CORE SESSION"
echo "=================================================="

# ---------- 1. Sanity: confirm we're in the right place ----------
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Not in the nova_tokenisation-core project root. Aborting."
    exit 1
fi

# ---------- 2. Ensure .gitignore excludes secrets & artifacts ----------
echo "📝 Writing .gitignore..."
cat > .gitignore <<'EOF'
# Secrets — NEVER commit
.env
*.env
!*.env.example

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.pytest_cache/
.mypy_cache/

# Node / Hardhat (if co-located)
node_modules/
artifacts/
cache/
typechain-types/

# OS
.DS_Store
Thumbs.db

# Local DB dumps (keep them out of git)
*.sql
nova_db_*.sql
EOF

# ---------- 3. Verify no secrets are staged ----------
echo "🔍 Scanning for accidentally tracked secrets..."
DANGER=$(git ls-files 2>/dev/null | grep -E '\.env$' || true)
if [ -n "$DANGER" ]; then
    echo "   ⚠️  WARNING: .env files are tracked by git:"
    echo "$DANGER"
    echo "   Untracking them (they remain on disk)..."
    git rm --cached $DANGER 2>/dev/null || true
fi

# ---------- 4. Init git if needed ----------
if [ ! -d ".git" ]; then
    echo "🆕 Initializing git repository..."
    git init
else
    echo "ℹ️  Git repository already initialized."
fi

# ---------- 5. Stage and commit ----------
echo "📦 Staging changes..."
git add -A

echo "📝 Committing..."
git commit -m "feat(layers 1-5): complete production-grade RWA core

Layers 1-5 frozen and verified on Base Mainnet.

Layer 2 (Tokenization):
  - NVP-1 (asset): 0x11b229E0F4a0DAee8B8Bf20BdED941b7ba4E8C4c
  - DKHYR (currency): 0x9991bE994829601F90328CCF9cee4D1A55ADae70

Layer 3 (Escrow):
  - BUY settlement: 0xe5df5a3de2dfe0718d2b42345d8a427141eddc65a7fdd05a913489c40024f3dd
  - SELL settlement: 0x0d5dd24477d2ca093b773fd6b253dc87085eff5352cdae5c3cd1ed75cd184ccc
  - Idempotency: duplicate deposit_tx_hash returns 409

Layer 4 (Sentinel):
  - Zero-trust auditor verifies every settlement against Base Mainnet
  - Token-aware matching (NVP-1 / DKHYR)
  - 3+ confirmation depth (reorg protection)
  - Postgres state: both orders VERIFIED

Layer 5 (Compliance):
  - FastAPI router: POST/GET /api/v1/compliance/whitelist
  - Postgres schema: kyc_whitelists, whitelist_sync_log
  - Solidity: PermissionedNVP.sol (pending on-chain deploy)
  - Default-deny semantics verified

Verified end-to-end:
  curl POST /whitelist            -> {status: success}
  curl GET  /whitelist/{wallet}   -> {whitelisted: true, jurisdiction: EU}
  curl GET  /whitelist/0x0...0    -> {whitelisted: false}

Pending (next session on VPS):
  - Deploy PermissionedNVP.sol (NVP-2) to Base Mainnet
  - Layer 6 (Regulatory Reporting)
  - Layer 7 (Telegram UI via nova-mcp)" || echo "ℹ️  Nothing to commit (working tree clean)."

# ---------- 6. Push ----------
echo "🚀 Pushing to origin..."
REMOTE=$(git remote get-url origin 2>/dev/null || echo "")
if [ -z "$REMOTE" ]; then
    echo "   ⚠️  No git remote configured."
    echo "   Run: git remote add origin <your-private-repo-url>"
    echo "   Then re-run: git push -u origin main"
else
    git push -u origin main 2>&1 | tail -5
fi

# ---------- 7. Database dump ----------
echo ""
echo "💾 Dumping Postgres database..."
TS=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="$HOME/nova_db_${TS}.sql"
docker compose exec -T postgres pg_dump -U nova nova_tokenisation > "$DUMP_FILE"
DUMP_SIZE=$(ls -lh "$DUMP_FILE" | awk '{print $5}')
echo "   ✅ Dumped to $DUMP_FILE ($DUMP_SIZE)"

# Sanity check — verify the verified orders are in the dump
if grep -q "ccac3c08-0256-4940-ad41-962a26c91029" "$DUMP_FILE"; then
    echo "   ✅ Verified order ccac3c08 found in dump"
else
    echo "   ⚠️  Order ccac3c08 NOT found in dump — investigate"
fi
if grep -q "7503a818-7c24-408f-b848-d44ddf6f27bc" "$DUMP_FILE"; then
    echo "   ✅ Verified order 7503a818 found in dump"
else
    echo "   ⚠️  Order 7503a818 NOT found in dump — investigate"
fi

# ---------- 8. Secrets snapshot (local only) ----------
echo ""
echo "🔐 Copying secrets to safe local filenames..."
cp .env "$HOME/nova_env_core_${TS}.txt" 2>/dev/null && echo "   ✅ ~/nova_env_core_${TS}.txt" || echo "   ⚠️  No .env found"
if [ -f "$HOME/NOVA/layer3/.env" ]; then
    cp "$HOME/NOVA/layer3/.env" "$HOME/nova_env_layer3_${TS}.txt"
    echo "   ✅ ~/nova_env_layer3_${TS}.txt"
fi

# ---------- 9. Contract registry ----------
echo ""
echo "📋 Writing contract registry..."
cat > "$HOME/nova_contracts_deployed.txt" <<EOF
# Nova Tokenisation Core — Deployed Contracts (Base Mainnet)
# Snapshot: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

NVP-1 (asset, plain ERC-20):   0x11b229E0F4a0DAee8B8Bf20BdED941b7ba4E8C4c
DKHYR (currency):              0x9991bE994829601F90328CCF9cee4D1A55ADae70
Treasury Wallet:               0xA4eE963F223C193261d8545e4c4681ED3837af25
Investor Wallet (Test):        0x66e9a79aDb97Bae948E97c09F1eE555f6E4c6767

NVP-2 (permissioned):          PENDING — deploy on VPS

# Verified Orders (Base Mainnet)
SELL ccac3c08:                 0x0d5dd24477d2ca093b773fd6b253dc87085eff5352cdae5c3cd1ed75cd184ccc
BUY  7503a818:                 0xe5df5a3de2dfe0718d2b42345d8a427141eddc65a7fdd05a913489c40024f3dd

# Layer Status
L1 (Identity):                 Scaffolded
L2 (Tokens):                   LIVE
L3 (Escrow):                   LIVE
L4 (Sentinel):                 LIVE
L5 (Compliance API):           LIVE
L5 (On-chain NVP-2):           PENDING
L6 (Regulatory Reporting):     PENDING (next session)
L7 (Client UI):                PENDING (next session)
EOF
echo "   ✅ ~/nova_contracts_deployed.txt"

# ---------- 10. Session log ----------
echo ""
echo "📜 Capturing session state..."
{
    echo "=== NOVA TOKENISATION CORE — SESSION LOG ==="
    echo "Timestamp: $(date -u)"
    echo ""
    echo "=== CONTAINERS ==="
    docker compose ps
    echo ""
    echo "=== RECENT SENTINEL LOGS ==="
    docker compose logs --tail=15 nova-sentinel 2>/dev/null || echo "(sentinel not running)"
    echo ""
    echo "=== VERIFIED ORDERS ==="
    docker compose exec -T postgres psql -U nova -d nova_tokenisation -c \
        "SELECT id, direction, state, audit_status, last_audited_at FROM escrow_orders ORDER BY created_at;" 2>/dev/null
    echo ""
    echo "=== WHITELIST STATE ==="
    docker compose exec -T postgres psql -U nova -d nova_tokenisation -c \
        "SELECT wallet_address, is_whitelisted, jurisdiction FROM kyc_whitelists;" 2>/dev/null
} > "$HOME/nova_session_log_${TS}.txt"
echo "   ✅ ~/nova_session_log_${TS}.txt"

# ---------- 11. Stop containers (preserve volumes) ----------
echo ""
echo "🛑 Stopping containers (volumes preserved)..."
docker compose stop
docker compose ps

# ---------- 12. Final summary ----------
echo ""
echo "=================================================="
echo "✅ SESSION FROZEN"
echo "=================================================="
echo ""
echo "📦 Snapshots in $HOME:"
ls -lh "$HOME"/nova_db_*.sql 2>/dev/null | tail -1
ls -lh "$HOME"/nova_env_*.txt 2>/dev/null | tail -2
ls -lh "$HOME"/nova_contracts_deployed.txt 2>/dev/null
ls -lh "$HOME"/nova_session_log_*.txt 2>/dev/null | tail -1
echo ""
echo "🐳 Docker containers:"
docker compose ps
echo ""
echo "💾 Disk state:"
df -h /var/lib/docker
echo ""
echo "🎯 Resume on VPS:"
echo "   1. git clone <your-private-repo>"
echo "   2. Copy .env back from ~/nova_env_core_*.txt"
echo "   3. Restore DB: cat ~/nova_db_*.sql | docker compose exec -T postgres psql -U nova nova_tokenisation"
echo "   4. docker compose up -d"
echo "   5. Deploy NVP-2: cd ~/NOVA/layer3 && npx hardhat run scripts/deploy_permissioned.js --network base"
echo ""
