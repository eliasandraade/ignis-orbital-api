import uuid
from datetime import date, datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from geoalchemy2.types import WKBElement
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

JURISDICTION_LEVELS = ("state", "municipality")


class ReferenceDataset(Base):
    """One official geographic dataset exactly as published (provenance record).

    Rows are identified by the SHA-256 of the published files, so re-importing
    the same files reuses the row and a corrected republication gets a new one.
    """

    __tablename__ = "reference_datasets"
    __table_args__ = (
        CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_reference_datasets_content_sha256_hex"
        ),
        CheckConstraint("feature_count > 0", name="ck_reference_datasets_feature_count_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    product: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_crs: Mapped[str] = mapped_column(String(32), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    files: Mapped[list] = mapped_column(JSONB, nullable=False)
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False)
    license_note: Mapped[str] = mapped_column(Text, nullable=False)
    importer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Jurisdiction(Base):
    """Official administrative boundary (IBGE): the state and its municipalities."""

    __tablename__ = "jurisdictions"
    __table_args__ = (
        CheckConstraint("level IN ('state', 'municipality')", name="ck_jurisdictions_level_known"),
        CheckConstraint(
            "(level = 'state' AND ibge_code ~ '^[0-9]{2}$' AND parent_id IS NULL)"
            " OR (level = 'municipality' AND ibge_code ~ '^[0-9]{7}$' AND parent_id IS NOT NULL)",
            name="ck_jurisdictions_code_matches_level",
        ),
        CheckConstraint(
            "left(ibge_code, 2) = state_ibge_code", name="ck_jurisdictions_code_in_state"
        ),
        CheckConstraint("official_area_km2 > 0", name="ck_jurisdictions_official_area_positive"),
        CheckConstraint(
            "ST_IsValid(geom) AND NOT ST_IsEmpty(geom)", name="ck_jurisdictions_geom_valid"
        ),
        Index("ix_jurisdictions_geom", "geom", postgresql_using="gist"),
        Index("ix_jurisdictions_level_state", "level", "state_ibge_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    ibge_code: Mapped[str] = mapped_column(String(7), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    state_ibge_code: Mapped[str] = mapped_column(String(2), nullable=False)
    state_abbreviation: Mapped[str] = mapped_column(String(2), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    official_area_km2: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    geom: Mapped[WKBElement] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reference_datasets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Every attribute of the published record, untouched, for audit.
    source_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
