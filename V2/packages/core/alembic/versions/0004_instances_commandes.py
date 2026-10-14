"""Instances and commands (batch D1): parameters, request fingerprint, per-actor idempotency key.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("instances", sa.Column("params", pg.JSONB, nullable=False, server_default="{}"))
    op.add_column("commands", sa.Column("request_hash", sa.Text, nullable=False, server_default=""))
    # A key only makes sense for its author: a global key would reveal others' keys.
    op.drop_constraint("uq_commands_idempotency_key", "commands", type_="unique")
    op.create_unique_constraint(
        "uq_commands_actor_idempotency_key", "commands", ["actor", "idempotency_key"]
    )
    op.create_index("ix_commands_status", "commands", ["status"])
    # The simulated engine always exists (the worker addresses it by its type).
    op.execute(
        "INSERT INTO engines (id, kind, image, version) "
        "SELECT gen_random_uuid(), 'fake', 'centrade/fake', '1' "
        "WHERE NOT EXISTS (SELECT 1 FROM engines WHERE kind = 'fake')"
    )


def downgrade() -> None:
    op.drop_index("ix_commands_status", "commands")
    op.drop_constraint("uq_commands_actor_idempotency_key", "commands", type_="unique")
    op.create_unique_constraint("uq_commands_idempotency_key", "commands", ["idempotency_key"])
    op.drop_column("commands", "request_hash")
    op.drop_column("instances", "params")
