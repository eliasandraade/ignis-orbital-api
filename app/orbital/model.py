import uuid
from datetime import datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from geoalchemy2.types import WKBElement
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SOURCES_SQL = "('NASA_FIRMS', 'INPE_QUEIMADAS')"
COUNTERS = (
    "records_fetched",
    "records_valid",
    "records_rejected",
    "records_out_of_scope",
    "records_inserted",
    "records_duplicate",
)


def _counter() -> Mapped[int]:
    return mapped_column(Integer, nullable=False, default=0, server_default="0")


class IngestionRun(Base):
    """One execution for one (source, product). Counters only ever describe
    what was committed: they change in the same transaction as the rows."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(f"source IN {SOURCES_SQL}", name="ck_ingestion_runs_source_known"),
        CheckConstraint(
            "status IN ('running', 'ok', 'partial', 'unavailable', 'disabled', 'error')",
            name="ck_ingestion_runs_status_known",
        ),
        CheckConstraint(
            "trigger IN ('schedule', 'manual')", name="ck_ingestion_runs_trigger_known"
        ),
        CheckConstraint(
            "(status = 'running') = (finished_at IS NULL)",
            name="ck_ingestion_runs_finished_iff_final",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_ingestion_runs_finished_after_start",
        ),
        CheckConstraint(
            "window_start IS NULL OR window_end IS NULL OR window_end > window_start",
            name="ck_ingestion_runs_window_ordered",
        ),
        *(
            CheckConstraint(f"{name} >= 0", name=f"ck_ingestion_runs_{name}_non_negative")
            for name in COUNTERS
        ),
        CheckConstraint(
            "records_fetched = records_valid + records_rejected",
            name="ck_ingestion_runs_fetched_balance",
        ),
        CheckConstraint(
            "records_valid = records_inserted + records_duplicate + records_out_of_scope",
            name="ck_ingestion_runs_valid_balance",
        ),
        # Two overlapping executions for the same product are impossible.
        Index(
            "uq_ingestion_runs_one_running",
            "source",
            "product",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        Index("ix_ingestion_runs_source_product_started", "source", "product", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_fetched: Mapped[int] = _counter()
    records_valid: Mapped[int] = _counter()
    records_rejected: Mapped[int] = _counter()
    records_out_of_scope: Mapped[int] = _counter()
    records_inserted: Mapped[int] = _counter()
    records_duplicate: Mapped[int] = _counter()
    # Stable, secret-free code and a sanitised message (never a URL with a key).
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class OrbitalDetection(Base):
    """A satellite thermal anomaly ("foco de calor"), never a confirmed fire."""

    __tablename__ = "orbital_detections"
    __table_args__ = (
        CheckConstraint(f"source IN {SOURCES_SQL}", name="ck_orbital_detections_source_known"),
        CheckConstraint(
            "ST_IsValid(location) AND NOT ST_IsEmpty(location)"
            " AND ST_X(location) BETWEEN -180 AND 180 AND ST_Y(location) BETWEEN -90 AND 90",
            name="ck_orbital_detections_location_valid",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence IN ('low', 'nominal', 'high')",
            name="ck_orbital_detections_confidence_known",
        ),
        CheckConstraint(
            "daynight IS NULL OR daynight IN ('D', 'N')",
            name="ck_orbital_detections_daynight_known",
        ),
        CheckConstraint("frp_mw IS NULL OR frp_mw >= 0", name="ck_orbital_detections_frp"),
        CheckConstraint(
            "brightness_k IS NULL OR brightness_k > 0", name="ck_orbital_detections_brightness"
        ),
        Index("ix_orbital_detections_location", "location", postgresql_using="gist"),
        Index("ix_orbital_detections_observed_at", "observed_at"),
        Index("ix_orbital_detections_source_observed_at", "source", "observed_at"),
        Index("ix_orbital_detections_jurisdiction_observed_at", "jurisdiction_id", "observed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    dedup_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    satellite: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[WKBElement] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=False
    )
    confidence: Mapped[str | None] = mapped_column(String(8), nullable=True)
    frp_mw: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    brightness_k: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    daynight: Mapped[str | None] = mapped_column(String(1), nullable=True)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jurisdictions.id", ondelete="RESTRICT"), nullable=False
    )
    # The run that first stored this observation (later runs count it as duplicate).
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
