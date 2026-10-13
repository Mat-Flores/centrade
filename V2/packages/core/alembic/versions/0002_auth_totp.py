"""Auth : anti-rejeu TOTP et date de la dernière vérification TOTP d'une session.

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
    # Dernier pas TOTP accepté : un code de ce pas, ou d'un pas antérieur, est refusé.
    op.add_column("users", sa.Column("totp_last_step", sa.BigInteger))
    op.add_column("sessions", sa.Column("totp_verified_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("sessions", "totp_verified_at")
    op.drop_column("users", "totp_last_step")
