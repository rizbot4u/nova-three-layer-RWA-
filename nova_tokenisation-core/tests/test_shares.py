import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import engine, Base
from app import models  # noqa: registers models with Base


@pytest_asyncio.fixture(autouse=True)
async def _setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_cannot_exceed_total_supply():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        inv = await client.post(
            "/api/v1/identity/investors",
            json={"email": "cap@test.com", "full_name": "Cap Test", "country": "GB"},
        )
        assert inv.status_code == 201, inv.text
        investor_id = inv.json()["id"]

        prop = await client.post(
            "/api/v1/property/properties",
            json={"address": "Test Road", "postcode": "LS1 1AA",
                  "valuation_gbp": 100000, "total_supply": 100},
        )
        assert prop.status_code == 201, prop.text
        property_id = prop.json()["id"]

        await client.post(f"/api/v1/property/properties/{property_id}/activate")

        ok = await client.post(
            "/api/v1/shares/issue",
            json={"property_id": property_id, "investor_id": investor_id, "amount": 100},
        )
        assert ok.status_code == 201, ok.text

        fail = await client.post(
            "/api/v1/shares/issue",
            json={"property_id": property_id, "investor_id": investor_id, "amount": 1},
        )
        assert fail.status_code == 400
        assert "Exceeds fixed total supply" in fail.json()["detail"]
