"""Instances : référence du secret `engine_api` (identifiants de l'API native du moteur).

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instances",
        sa.Column("engine_secret_ref", sa.Uuid, sa.ForeignKey("secrets.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instances", "engine_secret_ref")
