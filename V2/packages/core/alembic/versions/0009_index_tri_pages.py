"""Index for sorting the GET /orders pages (created_at, id) and GET /trades (closed_at, id).

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_orders_created_at_id", "orders", ["created_at", "id"])
    op.create_index("ix_trades_closed_at_id", "trades", ["closed_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_trades_closed_at_id", table_name="trades")
    op.drop_index("ix_orders_created_at_id", table_name="orders")
