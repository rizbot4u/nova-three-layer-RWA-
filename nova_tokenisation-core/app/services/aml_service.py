from app.config import settings
from app.utils.audit import write_audit_event

SANCTIONS_LIST = {"NORTH_KOREA", "IRAN", "SYRIA", "CUBA"}

class AMLService:
    async def screen_investor(self, investor_id: str, country: str) -> dict:
        risk_score = 0
        flags = []
        if country in SANCTIONS_LIST:
            risk_score = 100
            flags.append("sanctions_country")
        result = {
            "investor_id": investor_id,
            "risk_score": risk_score,
            "flags": flags,
            "provider": settings.AML_PROVIDER,
        }
        await write_audit_event("aml.screening", result)
        return result

aml_service = AMLService()
