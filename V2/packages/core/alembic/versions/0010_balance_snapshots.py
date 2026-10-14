"""balance_snapshots: last observed balance per instance and currency (no history).

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
NUM = sa.Numeric(38, 18)


def upgrade() -> None:
    op.create_table(
        "balance_snapshots",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("free", NUM, nullable=False),
        sa.Column("total", NUM, nullable=False),
        sa.Column("observed_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["instances.id"], name="fk_balance_snapshots_instance_id_instances"
        ),
        sa.UniqueConstraint(
            "instance_id", "currency", name="uq_balance_snapshots_instance_id_currency"
        ),
    )
    op.create_index("ix_balance_snapshots_instance_id", "balance_snapshots", ["instance_id"])


def downgrade() -> None:
    # Derived projection: the worker's next snapshot rebuilds it after an upgrade.
    op.drop_index("ix_balance_snapshots_instance_id", table_name="balance_snapshots")
    op.drop_table("balance_snapshots")
