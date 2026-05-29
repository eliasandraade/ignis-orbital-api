import uuid
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ESGReport(Base):
    __tablename__ = "esg_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    protected_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("protected_areas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    monitored_area_ha: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    incidents_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_response_minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    heat_spots_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vegetation_loss_estimated_ha: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    prevented_impact_estimate: Mapped[str | None] = mapped_column(Text, nullable=True)
    ods: Mapped[dict[str, bool] | None] = mapped_column(
        JSON, nullable=True
    )  # {"ods_2": True, "ods_15": True, ...}
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
