"""Commands: arguments (position to close, entry order to cancel).

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commands", sa.Column("args", JSONB))


def downgrade() -> None:
    op.drop_column("commands", "args")
