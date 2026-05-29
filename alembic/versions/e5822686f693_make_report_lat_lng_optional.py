"""make report lat lng optional

Revision ID: e5822686f693
Revises: a012
Create Date: 2026-05-29 19:14:22.652822

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5822686f693'
down_revision: Union[str, None] = 'a012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('public_reports', 'latitude',
                    existing_type=sa.DOUBLE_PRECISION(precision=53),
                    nullable=True)
    op.alter_column('public_reports', 'longitude',
                    existing_type=sa.DOUBLE_PRECISION(precision=53),
                    nullable=True)


def downgrade() -> None:
    op.alter_column('public_reports', 'longitude',
                    existing_type=sa.DOUBLE_PRECISION(precision=53),
                    nullable=False)
    op.alter_column('public_reports', 'latitude',
                    existing_type=sa.DOUBLE_PRECISION(precision=53),
                    nullable=False)
