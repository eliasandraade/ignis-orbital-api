"""geo foundation: reference_datasets, jurisdictions, ingestion_runs, orbital_detections

Revision ID: a013
Revises: 438a82832b4f
Create Date: 2026-11-03 00:00:00.000000

Official IBGE boundaries (SRID 4326, valid geometries, GiST) and the storage
of satellite thermal anomalies with run counters that balance by constraint.
Reversible: downgrade drops only what this revision created.
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a013"
down_revision: str | None = "438a82832b4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCES = "('NASA_FIRMS', 'INPE_QUEIMADAS')"
COUNTERS = (
    "records_fetched",
    "records_valid",
    "records_rejected",
    "records_out_of_scope",
    "records_inserted",
    "records_duplicate",
)


def _timestamp(name: str, nullable: bool = False, default: bool = True) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=sa.text("now()") if default else None,
    )


def upgrade() -> None:
    op.create_table(
        "reference_datasets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("product", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("source_crs", sa.String(32), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("files", postgresql.JSONB(), nullable=False),
        sa.Column("feature_count", sa.Integer(), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=False),
        sa.Column("importer_version", sa.String(32), nullable=False),
        _timestamp("imported_at"),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_reference_datasets_content_sha256_hex"
        ),
        sa.CheckConstraint(
            "feature_count > 0", name="ck_reference_datasets_feature_count_positive"
        ),
    )

    op.create_table(
        "jurisdictions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("ibge_code", sa.String(7), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("state_ibge_code", sa.String(2), nullable=False),
        sa.Column("state_abbreviation", sa.String(2), nullable=False),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jurisdictions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("official_area_km2", sa.Numeric(12, 3), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False
            ),
            nullable=False,
        ),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reference_datasets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_attributes", postgresql.JSONB(), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "level IN ('state', 'municipality')", name="ck_jurisdictions_level_known"
        ),
        sa.CheckConstraint(
            "(level = 'state' AND ibge_code ~ '^[0-9]{2}$' AND parent_id IS NULL)"
            " OR (level = 'municipality' AND ibge_code ~ '^[0-9]{7}$' AND parent_id IS NOT NULL)",
            name="ck_jurisdictions_code_matches_level",
        ),
        sa.CheckConstraint(
            "left(ibge_code, 2) = state_ibge_code", name="ck_jurisdictions_code_in_state"
        ),
        sa.CheckConstraint("official_area_km2 > 0", name="ck_jurisdictions_official_area_positive"),
        sa.CheckConstraint(
            "ST_IsValid(geom) AND NOT ST_IsEmpty(geom)", name="ck_jurisdictions_geom_valid"
        ),
    )
    op.create_index("ix_jurisdictions_geom", "jurisdictions", ["geom"], postgresql_using="gist")
    op.create_index("ix_jurisdictions_level_state", "jurisdictions", ["level", "state_ibge_code"])
    op.create_index("ix_jurisdictions_parent_id", "jurisdictions", ["parent_id"])
    op.create_index("ix_jurisdictions_dataset_id", "jurisdictions", ["dataset_id"])

    op.create_table(
        "ingestion_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("product", sa.String(64), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column(
            "triggered_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        _timestamp("started_at"),
        _timestamp("finished_at", nullable=True, default=False),
        _timestamp("window_start", nullable=True, default=False),
        _timestamp("window_end", nullable=True, default=False),
        *(sa.Column(name, sa.Integer(), nullable=False, server_default="0") for name in COUNTERS),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column(
            "params", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.CheckConstraint(f"source IN {SOURCES}", name="ck_ingestion_runs_source_known"),
        sa.CheckConstraint(
            "status IN ('running', 'ok', 'partial', 'unavailable', 'disabled', 'error')",
            name="ck_ingestion_runs_status_known",
        ),
        sa.CheckConstraint(
            "trigger IN ('schedule', 'manual')", name="ck_ingestion_runs_trigger_known"
        ),
        sa.CheckConstraint(
            "(status = 'running') = (finished_at IS NULL)",
            name="ck_ingestion_runs_finished_iff_final",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_ingestion_runs_finished_after_start",
        ),
        sa.CheckConstraint(
            "window_start IS NULL OR window_end IS NULL OR window_end > window_start",
            name="ck_ingestion_runs_window_ordered",
        ),
        *(
            sa.CheckConstraint(f"{name} >= 0", name=f"ck_ingestion_runs_{name}_non_negative")
            for name in COUNTERS
        ),
        sa.CheckConstraint(
            "records_fetched = records_valid + records_rejected",
            name="ck_ingestion_runs_fetched_balance",
        ),
        sa.CheckConstraint(
            "records_valid = records_inserted + records_duplicate + records_out_of_scope",
            name="ck_ingestion_runs_valid_balance",
        ),
    )
    op.create_index(
        "uq_ingestion_runs_one_running",
        "ingestion_runs",
        ["source", "product"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "ix_ingestion_runs_source_product_started",
        "ingestion_runs",
        ["source", "product", "started_at"],
    )

    op.create_table(
        "orbital_detections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("dedup_key", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("product", sa.String(64), nullable=False),
        sa.Column("satellite", sa.String(64), nullable=False),
        sa.Column("instrument", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("confidence", sa.String(8), nullable=True),
        sa.Column("frp_mw", sa.Numeric(10, 2), nullable=True),
        sa.Column("brightness_k", sa.Numeric(7, 2), nullable=True),
        sa.Column("daynight", sa.String(1), nullable=True),
        sa.Column(
            "jurisdiction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jurisdictions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        _timestamp("ingested_at"),
        sa.CheckConstraint(f"source IN {SOURCES}", name="ck_orbital_detections_source_known"),
        sa.CheckConstraint(
            "ST_IsValid(location) AND NOT ST_IsEmpty(location)"
            " AND ST_X(location) BETWEEN -180 AND 180 AND ST_Y(location) BETWEEN -90 AND 90",
            name="ck_orbital_detections_location_valid",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence IN ('low', 'nominal', 'high')",
            name="ck_orbital_detections_confidence_known",
        ),
        sa.CheckConstraint(
            "daynight IS NULL OR daynight IN ('D', 'N')",
            name="ck_orbital_detections_daynight_known",
        ),
        sa.CheckConstraint("frp_mw IS NULL OR frp_mw >= 0", name="ck_orbital_detections_frp"),
        sa.CheckConstraint(
            "brightness_k IS NULL OR brightness_k > 0", name="ck_orbital_detections_brightness"
        ),
    )
    op.create_index(
        "ix_orbital_detections_location",
        "orbital_detections",
        ["location"],
        postgresql_using="gist",
    )
    op.create_index("ix_orbital_detections_observed_at", "orbital_detections", ["observed_at"])
    op.create_index(
        "ix_orbital_detections_source_observed_at",
        "orbital_detections",
        ["source", "observed_at"],
    )
    op.create_index(
        "ix_orbital_detections_jurisdiction_observed_at",
        "orbital_detections",
        ["jurisdiction_id", "observed_at"],
    )
    op.create_index(
        "ix_orbital_detections_ingestion_run_id", "orbital_detections", ["ingestion_run_id"]
    )


def downgrade() -> None:
    op.drop_table("orbital_detections")
    op.drop_table("ingestion_runs")
    op.drop_table("jurisdictions")
    op.drop_table("reference_datasets")
