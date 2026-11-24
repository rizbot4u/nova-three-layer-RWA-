import uuid
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Enum, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Property(Base):
    __tablename__ = "properties"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    postcode: Mapped[str] = mapped_column(String(10), nullable=False)
    valuation_gbp: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total_supply: Mapped[int] = mapped_column(BigInteger, nullable=False, default=500_000_000)
    circulating_supply: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        Enum("draft", "active", "closed", name="property_status"),
        default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
