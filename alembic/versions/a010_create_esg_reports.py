"""create esg_reports table

Revision ID: a010
Revises: a009
Create Date: 2026-05-29 00:00:00.000000
"""

from collections.abc import Sequence

import geoalchemy2  # noqa: F401
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a010"
down_revision: str | None = "a009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "esg_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "protected_area_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("protected_areas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("monitored_area_ha", sa.Float(), nullable=False, server_default="0"),
        sa.Column("incidents_resolved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "average_response_minutes",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("heat_spots_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "vegetation_loss_estimated_ha",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("prevented_impact_estimate", sa.Text(), nullable=True),
        sa.Column("ods", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_esg_reports_protected_area_id", "esg_reports", ["protected_area_id"])


def downgrade() -> None:
    op.drop_index("ix_esg_reports_protected_area_id", table_name="esg_reports")
    op.drop_table("esg_reports")
