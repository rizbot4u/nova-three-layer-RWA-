from fastapi import FastAPI
from app.api import identity, property, shares, watchlist
from app.routers import escrow, settlement_v2
from app.compliance.router import router as compliance_router
from app.reporting.router import router as reporting_router

app = FastAPI(
    title="Nova Tokenisation Core",
    description="Layer 1 (Identity) + Layer 2 (Tokenisation) + Layer 3 (Escrow).",
    version="0.3.0",
)

# Include all routers
app.include_router(compliance_router)
app.include_router(reporting_router)
app.include_router(identity.router)
app.include_router(property.router)
app.include_router(shares.router)
app.include_router(escrow.router)
app.include_router(settlement_v2.router)
app.include_router(watchlist.router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "nova-tokenisation-core", "layer": "1+2+3"}
