"""Auth: TOTP anti-replay and date of a session's last TOTP verification.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Last accepted TOTP step: a code from this step, or an earlier one, is refused.
    op.add_column("users", sa.Column("totp_last_step", sa.BigInteger))
    op.add_column("sessions", sa.Column("totp_verified_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("sessions", "totp_verified_at")
    op.drop_column("users", "totp_last_step")
