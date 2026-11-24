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
