import uuid
from datetime import datetime
from uuid import uuid4

from geoalchemy2 import Geometry
from geoalchemy2.types import WKBElement
from sqlalchemy import Float, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class ProtectedArea(Base):
    __tablename__ = "protected_areas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # ProtectedAreaCategory
    municipality: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    organ: Mapped[str] = mapped_column(String(255), nullable=False)
    area_ha: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(
        String(255), nullable=False, default="base demonstrativa acadêmica"
    )
    data_quality: Mapped[str] = mapped_column(
        String(20), nullable=False, default="estimated"
    )  # DataQuality
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    geometry: Mapped[WKBElement | None] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326), nullable=True
    )
    buffer_zone: Mapped[WKBElement | None] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326), nullable=True
    )
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)
