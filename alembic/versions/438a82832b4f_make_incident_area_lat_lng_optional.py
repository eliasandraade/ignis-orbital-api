"""make_incident_area_lat_lng_optional

Revision ID: 438a82832b4f
Revises: e5822686f693
Create Date: 2026-05-29 20:08:40.862352

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '438a82832b4f'
down_revision: str | None = 'e5822686f693'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column('incidents', 'protected_area_id',
                    existing_type=sa.UUID(),
                    nullable=True)
    op.drop_constraint('incidents_protected_area_id_fkey', 'incidents', type_='foreignkey')
    op.create_foreign_key(
        'incidents_protected_area_id_fkey',
        'incidents', 'protected_areas',
        ['protected_area_id'], ['id'],
        ondelete='SET NULL',
    )
    op.alter_column('incidents', 'latitude',
                    existing_type=sa.DOUBLE_PRECISION(precision=53),
                    nullable=True)
    op.alter_column('incidents', 'longitude',
                    existing_type=sa.DOUBLE_PRECISION(precision=53),
                    nullable=True)


def downgrade() -> None:
    op.alter_column('incidents', 'longitude',
                    existing_type=sa.DOUBLE_PRECISION(precision=53),
                    nullable=False)
    op.alter_column('incidents', 'latitude',
                    existing_type=sa.DOUBLE_PRECISION(precision=53),
                    nullable=False)
    op.drop_constraint('incidents_protected_area_id_fkey', 'incidents', type_='foreignkey')
    op.create_foreign_key(
        'incidents_protected_area_id_fkey',
        'incidents', 'protected_areas',
        ['protected_area_id'], ['id'],
        ondelete='RESTRICT',
    )
    op.alter_column('incidents', 'protected_area_id',
                    existing_type=sa.UUID(),
                    nullable=False)
