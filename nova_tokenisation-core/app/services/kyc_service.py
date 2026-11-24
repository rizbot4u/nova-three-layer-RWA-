from app.config import settings
from app.utils.audit import write_audit_event

class KYCService:
    async def verify_identity(self, investor_id: str, full_name: str, country: str) -> dict:
        if settings.KYC_PROVIDER == "mock":
            result = {"investor_id": investor_id, "status": "verified", "provider": "mock"}
        else:
            raise NotImplementedError(f"KYC provider {settings.KYC_PROVIDER} not yet integrated")
        await write_audit_event("kyc.verification", result)
        return result

kyc_service = KYCService()
