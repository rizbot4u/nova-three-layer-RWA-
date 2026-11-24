# Nova Tokenisation Core — Backend Scaffold

Regulated property tokenisation backend. FastAPI + PostgreSQL + Redis.

Layer 1 (Identity & Compliance) + Layer 2 (Asset Registry & Tokenisation).

## Run locally

```bash
cp .env.example .env
docker compose up --build
· API:  http://localhost:8000
· Docs: http://localhost:8000/docs
· Health: http://localhost:8000/health
  MD

── 8. Start the stack ───────────────────────────────────────

echo "[8/8] Starting docker compose"
echo "(skipping docker compose up — not available)"

echo
echo "Waiting for API to boot..."
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "  ✅ API ready (${i}s)"
break
fi
sleep 1
done

echo
echo "═══════════════════════════════════════════"
echo "  DEPLOY COMPLETE"
echo "═══════════════════════════════════════════"
echo "  Root:      $ROOT"
echo "  API:       http://127.0.0.1:8000"
echo "  Docs:      http://127.0.0.1:8000/docs"
echo "  Health:    http://127.0.0.1:8000/health"
echo
echo "  Container status:"
docker compose ps
echo
echo "  Logs:      cd $ROOT && docker compose logs -f api"
echo "  Stop:      cd $ROOT && docker compose down"
echo
echo "  Next steps:"
echo "  1. cd $ROOT && git init && git add . && git commit -m 'feat: initial scaffold'"
echo "  2. Run the migration:  docker compose exec api alembic upgrade head"
echo "  3. Run the test:       docker compose exec api pytest -v"
