"""create resources table

Revision ID: a007
Revises: a006
Create Date: 2026-05-29 00:00:00.000000
"""

from collections.abc import Sequence

import geoalchemy2  # noqa: F401
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a007"
down_revision: str | None = "a006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="available"),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column(
            "assigned_incident_id",
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
    op.create_index("ix_resources_type", "resources", ["type"])
    op.create_index("ix_resources_status", "resources", ["status"])


def downgrade() -> None:
    op.drop_index("ix_resources_status", table_name="resources")
    op.drop_index("ix_resources_type", table_name="resources")
    op.drop_table("resources")
