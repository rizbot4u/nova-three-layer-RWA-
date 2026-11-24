from sqlalchemy import Column, String, DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base


class RegulatoryReport(Base):
    __tablename__ = "regulatory_reports"

    id = Column(String, primary_key=True)
    report_type = Column(String, nullable=False)      # DAILY, MONTHLY, QUARTERLY, INVESTOR, WIND_DOWN
    jurisdiction = Column(String, nullable=False)     # UK, EU, UAE
    period_key = Column(String, nullable=False)       # 2026-10, 2026-Q3
    status = Column(String, default="GENERATED")      # GENERATED, FILED, FLAGGED
    payload = Column(JSONB, nullable=False)
    pdf_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AMLAlert(Base):
    __tablename__ = "aml_alerts"

    id = Column(String, primary_key=True)
    wallet_address = Column(String, nullable=False)
    trigger_reason = Column(String, nullable=False)
    risk_score = Column(Numeric(5, 2), default=0)
    status = Column(String, default="OPEN")            # OPEN, REVIEWED, REPORTED_SAR
    created_at = Column(DateTime(timezone=True), server_default=func.now())
