"""Registre : code source et clé d'idempotence d'une version de stratégie.

Le code entre dans les colonnes protégées par le trigger d'immuabilité.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_BODY = """
        BEGIN
            IF NEW.manifest IS DISTINCT FROM OLD.manifest
               OR NEW.code_hash IS DISTINCT FROM OLD.code_hash
               OR NEW.exits IS DISTINCT FROM OLD.exits{extra} THEN
                RAISE EXCEPTION '{msg}';
            END IF;
            RETURN NEW;
        END $$"""


def _function(extra: str, msg: str) -> str:
    return (
        "CREATE OR REPLACE FUNCTION strategy_versions_immutable() RETURNS trigger "
        "LANGUAGE plpgsql AS $$" + _BODY.format(extra=extra, msg=msg)
    )


def upgrade() -> None:
    op.add_column(
        "strategy_versions", sa.Column("code", sa.Text, nullable=False, server_default="")
    )
    op.alter_column("strategy_versions", "code", server_default=None)
    op.add_column("strategy_versions", sa.Column("idempotency_key", sa.Text))
    op.create_unique_constraint(
        "uq_strategy_versions_strategy_id_idempotency_key",
        "strategy_versions",
        ["strategy_id", "idempotency_key"],
    )
    op.execute(
        _function(
            "\n               OR NEW.code IS DISTINCT FROM OLD.code",
            "strategy_versions: manifest, code, code_hash et exits sont immuables",
        )
    )


def downgrade() -> None:
    op.execute(_function("", "strategy_versions: manifest, code_hash et exits sont immuables"))
    op.drop_constraint(
        "uq_strategy_versions_strategy_id_idempotency_key", "strategy_versions", type_="unique"
    )
    op.drop_column("strategy_versions", "idempotency_key")
    op.drop_column("strategy_versions", "code")
