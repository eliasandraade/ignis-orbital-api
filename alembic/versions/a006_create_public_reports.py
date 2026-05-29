"""create public_reports table

Revision ID: a006
Revises: a005
Create Date: 2026-05-29 00:00:00.000000
"""

from collections.abc import Sequence

import geoalchemy2  # noqa: F401
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a006"
down_revision: str | None = "a005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "public_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("protocol", sa.String(30), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("urgency", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reporter_name", sa.String(255), nullable=True),
        sa.Column("contact", sa.String(255), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column(
            "protected_area_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("protected_areas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("evidence_urls", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_notes", sa.Text(), nullable=True),
        sa.Column(
            "linked_incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_public_reports_protocol", "public_reports", ["protocol"], unique=True)
    op.create_index("ix_public_reports_type", "public_reports", ["type"])
    op.create_index("ix_public_reports_status", "public_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_public_reports_status", table_name="public_reports")
    op.drop_index("ix_public_reports_type", table_name="public_reports")
    op.drop_index("ix_public_reports_protocol", table_name="public_reports")
    op.drop_table("public_reports")
