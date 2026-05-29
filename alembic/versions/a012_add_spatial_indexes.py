"""add spatial gist indexes

Revision ID: a012
Revises: a011
Create Date: 2026-05-29 00:00:00.000000
"""

from collections.abc import Sequence

import geoalchemy2  # noqa: F401

from alembic import op

revision: str = "a012"
down_revision: str | None = "a011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_protected_areas_geometry",
        "protected_areas",
        ["geometry"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_protected_areas_buffer_zone",
        "protected_areas",
        ["buffer_zone"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_incidents_location",
        "incidents",
        ["location"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_public_reports_location",
        "public_reports",
        ["location"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_evidence_location",
        "evidence",
        ["location"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_location", table_name="evidence")
    op.drop_index("ix_public_reports_location", table_name="public_reports")
    op.drop_index("ix_incidents_location", table_name="incidents")
    op.drop_index("ix_protected_areas_buffer_zone", table_name="protected_areas")
    op.drop_index("ix_protected_areas_geometry", table_name="protected_areas")
