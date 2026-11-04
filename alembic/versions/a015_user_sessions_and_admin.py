"""users: session revocation, last login, optimistic locking, forced password change

Revision ID: a015
Revises: a014
Create Date: 2026-11-04 00:00:00.000000

- session_version: copied into each JWT ("sv"); bumping it revokes every
  token already issued to that user (role change, deactivation, reset).
- row_version: optimistic locking for administrative edits (409 on mismatch).
- last_login_at: real time of the last successful login (null = never).
- must_change_password: set by an administrative reset; the user can only
  change the password until it is cleared.
- uq_users_email_lower: e-mail uniqueness regardless of letter case.
Reversible: downgrade drops only these objects.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a015"
down_revision: str | None = "a014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "users", sa.Column("row_version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "row_version")
    op.drop_column("users", "session_version")
