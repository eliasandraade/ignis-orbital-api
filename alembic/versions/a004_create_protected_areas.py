"""create protected_areas table

Revision ID: a004
Revises: a003
Create Date: 2026-05-29 00:00:00.000000
"""

from collections.abc import Sequence

import geoalchemy2  # noqa: F401
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a004"
down_revision: str | None = "a003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "protected_areas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("municipality", sa.String(255), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("organ", sa.String(255), nullable=False),
        sa.Column("area_ha", sa.Float(), nullable=False),
        sa.Column(
            "source",
            sa.String(255),
            nullable=False,
            server_default="base demonstrativa acadêmica",
        ),
        sa.Column(
            "data_quality",
            sa.String(20),
            nullable=False,
            server_default="estimated",
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=True,
        ),
        sa.Column(
            "buffer_zone",
            geoalchemy2.types.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=True,
        ),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lng", sa.Float(), nullable=False),
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
    op.create_index("ix_protected_areas_name", "protected_areas", ["name"])
    op.create_index("ix_protected_areas_category", "protected_areas", ["category"])
    op.create_index("ix_protected_areas_state", "protected_areas", ["state"])


def downgrade() -> None:
    op.drop_index("ix_protected_areas_state", table_name="protected_areas")
    op.drop_index("ix_protected_areas_category", table_name="protected_areas")
    op.drop_index("ix_protected_areas_name", table_name="protected_areas")
    op.drop_table("protected_areas")
