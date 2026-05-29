"""create evidence table

Revision ID: a009
Revises: a008
Create Date: 2026-05-29 00:00:00.000000
"""

from collections.abc import Sequence

import geoalchemy2  # noqa: F401
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a009"
down_revision: str | None = "a008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public_reports.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_evidence_incident_id", "evidence", ["incident_id"])
    op.create_index("ix_evidence_report_id", "evidence", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_report_id", table_name="evidence")
    op.drop_index("ix_evidence_incident_id", table_name="evidence")
    op.drop_table("evidence")
