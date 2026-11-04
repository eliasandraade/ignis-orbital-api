"""detection provenance: sensor-specific confidence/brightness and provider ids

Revision ID: a014
Revises: a013
Create Date: 2026-11-04 00:00:00.000000

FIRMS documents different indicators per sensor: VIIRS confidence is a class
(low/nominal/high) while MODIS confidence is a 0-100 percentage with no
published class boundaries; VIIRS brightness is the I-4 channel and MODIS
brightness channel 21/22. Separate columns keep them apart instead of
inventing an equivalence. provider_record_id keeps the provider's own id
(INPE foco_id). Reversible: downgrade drops only these columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a014"
down_revision: str | None = "a013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "orbital_detections"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("confidence_pct", sa.SmallInteger(), nullable=True))
    op.add_column(TABLE, sa.Column("brightness_channel", sa.String(16), nullable=True))
    op.add_column(TABLE, sa.Column("provider_record_id", sa.String(64), nullable=True))
    op.create_check_constraint(
        "ck_orbital_detections_confidence_pct_range",
        TABLE,
        "confidence_pct IS NULL OR confidence_pct BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_orbital_detections_brightness_channel_known",
        TABLE,
        "brightness_channel IS NULL OR brightness_channel IN ('VIIRS_I4', 'MODIS_21_22')",
    )
    op.create_check_constraint(
        "ck_orbital_detections_brightness_has_channel",
        TABLE,
        "(brightness_k IS NULL) = (brightness_channel IS NULL)",
    )
    op.create_check_constraint(
        "ck_orbital_detections_one_confidence_kind",
        TABLE,
        "confidence IS NULL OR confidence_pct IS NULL",
    )


def downgrade() -> None:
    for name in (
        "ck_orbital_detections_one_confidence_kind",
        "ck_orbital_detections_brightness_has_channel",
        "ck_orbital_detections_brightness_channel_known",
        "ck_orbital_detections_confidence_pct_range",
    ):
        op.drop_constraint(name, TABLE, type_="check")
    op.drop_column(TABLE, "provider_record_id")
    op.drop_column(TABLE, "brightness_channel")
    op.drop_column(TABLE, "confidence_pct")
