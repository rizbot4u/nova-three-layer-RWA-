#!/bin/bash
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"

echo "=================================================="
echo "🔒 HARDENING RUNTIME + FREEZING SESSION"
echo "=================================================="

# ---------- 1. Remove --reload from docker-compose.yml ----------
echo "🔧 Removing --reload from docker-compose.yml (vfs stability fix)..."

if grep -q "uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" docker-compose.yml; then
    cp docker-compose.yml "docker-compose.yml.bak.$(date +%s)"
    sed -i 's|uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload|uvicorn app.main:app --host 0.0.0.0 --port 8000|g' docker-compose.yml
    echo "   ✅ --reload removed."
else
    echo "   ℹ️  --reload already absent."
fi

# Verify
grep -n "uvicorn" docker-compose.yml

# ---------- 2. Apply the change ----------
echo ""
echo "🔄 Recreating api container with stable command..."
docker compose up -d --force-recreate api
sleep 8
docker compose ps api

# ---------- 3. Re-verify all 6 layers post-hardening ----------
echo ""
echo "═══════════════ LAYER 3: ESCROW ═══════════════"
curl -sS http://127.0.0.1:8100/health | python3 -m json.tool

echo ""
echo "═══════════════ LAYER 5: COMPLIANCE ═══════════════"
curl -sS http://127.0.0.1:8100/api/v1/compliance/whitelist/0x66e9a79aDb97Bae948E97c09F1eE555f6E4c6767 | python3 -m json.tool

echo ""
echo "═══════════════ LAYER 6: REPORTING (3 endpoints) ═══════════════"
echo "→ Daily:"
curl -sS http://127.0.0.1:8100/api/v1/reporting/daily/2026-10-13 | python3 -m json.tool
echo ""
echo "→ AML:"
curl -sS http://127.0.0.1:8100/api/v1/reporting/aml/alerts | python3 -m json.tool
echo ""
echo "→ Wind-down:"
curl -sS http://127.0.0.1:8100/api/v1/reporting/wind-down | python3 -m json.tool

echo ""
echo "═══════════════ LAYER 4: SENTINEL ═══════════════"
docker compose logs --tail=3 nova-sentinel

echo ""
echo "═══════════════ CONTAINERS ═══════════════"
docker compose ps

echo ""
echo "═══════════════ DISK ═══════════════"
df -h /var/lib/docker | tail -1

# ---------- 4. Freeze session ----------
echo ""
echo "=================================================="
echo "🧊 FREEZING SESSION"
echo "=================================================="

./freeze_session.sh
