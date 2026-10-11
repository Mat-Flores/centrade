"""positions : identifiant du moteur (plusieurs positions sur un même instrument).

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("positions", sa.Column("external_id", sa.Text))
    op.execute("UPDATE positions SET external_id = id::text")
    op.alter_column("positions", "external_id", nullable=False)
    op.drop_constraint("uq_positions_instance_instrument_side", "positions", type_="unique")
    op.create_unique_constraint(
        "uq_positions_instance_id_external_id", "positions", ["instance_id", "external_id"]
    )


def downgrade() -> None:
    # Deux positions d'un même instrument violeraient l'ancienne unicité. `positions` est une
    # projection dérivée : on la vide, le prochain relevé du worker la reconstruit.
    op.execute("DELETE FROM positions")
    op.drop_constraint("uq_positions_instance_id_external_id", "positions", type_="unique")
    op.create_unique_constraint(
        "uq_positions_instance_instrument_side", "positions", ["instance_id", "instrument", "side"]
    )
    op.drop_column("positions", "external_id")
