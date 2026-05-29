import uuid
from datetime import UTC, datetime
from uuid import uuid4

from geoalchemy2 import Geometry
from geoalchemy2.types import WKBElement
from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PublicReport(Base):
    __tablename__ = "public_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    protocol: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # ReportType
    description: Mapped[str] = mapped_column(Text, nullable=False)
    urgency: Mapped[str] = mapped_column(String(20), nullable=False)  # ReportUrgency
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )  # ReportStatus
    reporter_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location: Mapped[WKBElement | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    protected_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("protected_areas.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence_urls: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=list)
    validation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
