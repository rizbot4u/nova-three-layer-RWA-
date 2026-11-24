import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import Base, engine
from app.main import app
from app import models  # noqa: registers models


@pytest_asyncio.fixture(autouse=True)
async def _setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_full_escrow_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create escrow order (no on-chain dependency yet)
        create = await client.post(
            "/api/v1/escrow/create",
            json={
                "investor_wallet": "0x1111111111111111111111111111111111111111",
                "property_contract": "0xb27d7b836939CbFaaA1E744BB3145a5e424eEb89",
                "share_amount": 10,
                "price_per_share_usd": 100.0,
            },
        )
        assert create.status_code == 201, create.text
        order_id = create.json()["order_id"]
        assert create.json()["state"] == "pending"

        # 2. Fund
        fund = await client.post(
            f"/api/v1/escrow/{order_id}/fund",
            params={"deposit_tx_hash": "0xdeadbeef"},
        )
        assert fund.status_code == 200, fund.text
        assert fund.json()["state"] == "funded"

        # 3. Cannot fund twice
        fund_again = await client.post(
            f"/api/v1/escrow/{order_id}/fund",
            params={"deposit_tx_hash": "0xdeadbeef"},
        )
        assert fund_again.status_code == 400

        # 4. Cancel before settle (allowed)
        cancel = await client.post(f"/api/v1/escrow/{order_id}/cancel")
        assert cancel.status_code == 200
        assert cancel.json()["state"] == "cancelled"

        # 5. Cannot settle a cancelled order
        settle = await client.post(f"/api/v1/escrow/{order_id}/settle")
        assert settle.status_code == 400

        # 6. Read back
        detail = await client.get(f"/api/v1/escrow/{order_id}")
        assert detail.status_code == 200
        assert detail.json()["state"] == "cancelled"
