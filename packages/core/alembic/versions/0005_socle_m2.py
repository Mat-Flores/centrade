"""Socle de données de M2 : comptes, secrets, stratégies, trades, jetons de service, déploiement.

Revision ID: 0005
Revises: 0004
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
NUM = sa.Numeric(38, 18)
NOW = sa.text("now()")


def _id() -> sa.Column[Any]:
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True)


def _uuid(name: str, **kw: Any) -> sa.Column[Any]:
    return sa.Column(name, pg.UUID(as_uuid=True), **kw)


def _stamps() -> list[sa.Column[Any]]:
    return [
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
    ]


def _in(col: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{col} IN ({', '.join(repr(v) for v in values)})", name=name)


def upgrade() -> None:
    op.create_table(
        "secrets",
        _id(),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("usage", sa.Text, nullable=False),
        sa.Column("ciphertext", sa.LargeBinary, nullable=False),
        sa.Column("nonce", sa.LargeBinary, nullable=False),
        sa.Column("key_version", sa.Integer, nullable=False),
        sa.Column("last_used_at", TS),
        sa.Column("rotated_at", TS),
        *_stamps(),
        _in("usage", ("trade", "read", "engine_api", "webhook"), "usage"),
    )
    op.create_table(
        "accounts",
        _id(),
        sa.Column("venue", sa.Text, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("environment", sa.Text, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("capital_cap", NUM),
        _uuid("secret_ref"),
        _uuid("read_secret_ref"),
        sa.Column("permissions_verified_at", TS),
        sa.Column("ip_restricted", sa.Boolean),
        *_stamps(),
        sa.ForeignKeyConstraint(
            ["secret_ref"], ["secrets.id"], name="fk_accounts_secret_ref_secrets"
        ),
        sa.ForeignKeyConstraint(
            ["read_secret_ref"], ["secrets.id"], name="fk_accounts_read_secret_ref_secrets"
        ),
        _in("type", ("paper", "live"), "type"),
        _in("environment", ("production", "sandbox"), "environment"),
    )
    op.create_table(
        "strategies",
        _id(),
        sa.Column("name", sa.Text, nullable=False),
        *_stamps(),
        sa.UniqueConstraint("name", name="uq_strategies_name"),
    )
    op.create_table(
        "strategy_versions",
        _id(),
        _uuid("strategy_id", nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("manifest", pg.JSONB, nullable=False),
        sa.Column("code_hash", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("author", sa.Text, nullable=False),
        sa.Column("static_checks", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("exits", pg.JSONB, nullable=False),
        *_stamps(),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], name="fk_strategy_versions_strategy_id_strategies"
        ),
        sa.UniqueConstraint(
            "strategy_id", "version", name="uq_strategy_versions_strategy_id_version"
        ),
        _in("status", ("draft", "approved", "retired"), "status"),
    )
    op.create_index("ix_strategy_versions_strategy_id", "strategy_versions", ["strategy_id"])
    # Une version déposée ne change plus (F1) : on en dépose une autre. Le statut reste modifiable.
    op.execute("""
        CREATE FUNCTION strategy_versions_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.manifest IS DISTINCT FROM OLD.manifest
               OR NEW.code_hash IS DISTINCT FROM OLD.code_hash
               OR NEW.exits IS DISTINCT FROM OLD.exits THEN
                RAISE EXCEPTION 'strategy_versions: manifest, code_hash et exits sont immuables';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute(
        "CREATE TRIGGER strategy_versions_immutable BEFORE UPDATE ON strategy_versions "
        "FOR EACH ROW EXECUTE FUNCTION strategy_versions_immutable()"
    )

    op.add_column("engines", sa.Column("memory_reservation_mb", sa.Integer))
    op.add_column("engines", sa.Column("cpu_reservation", NUM))
    op.add_column("instances", _uuid("strategy_version_id"))
    op.add_column("instances", _uuid("account_id"))
    op.add_column("instances", sa.Column("limits", pg.JSONB, nullable=False, server_default="{}"))
    op.add_column("instances", sa.Column("container_ref", sa.Text))
    op.add_column("instances", sa.Column("deployment_fingerprint", sa.Text))
    op.add_column("instances", sa.Column("config_hash", sa.Text))
    op.add_column("instances", sa.Column("effective_config", pg.JSONB))
    op.add_column("instances", sa.Column("effective_config_at", TS))
    op.add_column("instances", sa.Column("drift", pg.JSONB))
    op.add_column("instances", _uuid("paper_origin_id"))
    op.create_foreign_key(
        "fk_instances_strategy_version_id_strategy_versions",
        "instances", "strategy_versions", ["strategy_version_id"], ["id"],
    )  # fmt: skip
    op.create_foreign_key(
        "fk_instances_account_id_accounts", "instances", "accounts", ["account_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_instances_paper_origin_id_instances",
        "instances", "instances", ["paper_origin_id"], ["id"],
    )  # fmt: skip
    op.create_index("ix_instances_strategy_version_id", "instances", ["strategy_version_id"])
    op.create_index("ix_instances_account_id", "instances", ["account_id"])

    op.add_column("positions", sa.Column("stop_price", NUM))
    op.add_column("positions", sa.Column("stop_venue", sa.Text))
    op.add_column("positions", sa.Column("stop_type", sa.Text))
    op.add_column(
        "positions",
        sa.Column("protection_state", sa.Text, nullable=False, server_default="unknown"),
    )
    op.add_column("positions", sa.Column("protection_verified_at", TS))
    op.create_check_constraint(
        "ck_positions_stop_venue", "positions", "stop_venue IN ('venue', 'engine')"
    )
    op.create_check_constraint(
        "ck_positions_stop_type", "positions", "stop_type IN ('fixed', 'trailing', 'dynamic')"
    )
    op.create_check_constraint(
        "ck_positions_protection_state",
        "positions",
        "protection_state IN ('protected', 'engine_only', 'unprotected', 'unknown')",
    )

    op.create_table(
        "trades",
        _id(),
        _uuid("instance_id", nullable=False),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("instrument", sa.Text, nullable=False),
        sa.Column("quantity", NUM, nullable=False),
        sa.Column("entry_price", NUM, nullable=False),
        sa.Column("exit_price", NUM, nullable=False),
        sa.Column("entry_cause", sa.Text, nullable=False),
        sa.Column("exit_cause", sa.Text, nullable=False),
        sa.Column("pnl", NUM, nullable=False),
        sa.Column("fees", NUM, nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("opened_at", TS, nullable=False),
        sa.Column("closed_at", TS, nullable=False),
        sa.Column("duration_s", sa.Integer, nullable=False),
        *_stamps(),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["instances.id"], name="fk_trades_instance_id_instances"
        ),
        sa.UniqueConstraint("instance_id", "external_id", name="uq_trades_instance_id_external_id"),
        _in(
            "exit_cause",
            (
                "stop_loss",
                "trailing_stop",
                "take_profit",
                "signal",
                "timeout",
                "manual",
                "kill_switch",
                "engine_protection",
                "liquidation",
                "unknown",
            ),
            "exit_cause",
        ),
    )
    op.create_index("ix_trades_instance_id", "trades", ["instance_id"])

    op.create_table(
        "service_accounts",
        _id(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("scopes", pg.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("token_hash", sa.Text, nullable=False),
        _uuid("instance_id"),
        *_stamps(),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["instances.id"], name="fk_service_accounts_instance_id_instances"
        ),
        sa.UniqueConstraint("name", name="uq_service_accounts_name"),
        sa.UniqueConstraint("token_hash", name="uq_service_accounts_token_hash"),
    )
    op.create_index("ix_service_accounts_instance_id", "service_accounts", ["instance_id"])


def downgrade() -> None:
    op.drop_table("service_accounts")
    op.drop_table("trades")
    for c in (
        "protection_verified_at",
        "protection_state",
        "stop_type",
        "stop_venue",
        "stop_price",
    ):
        op.drop_column("positions", c)
    for c in (
        "paper_origin_id", "drift", "effective_config_at", "effective_config", "config_hash",
        "deployment_fingerprint", "container_ref", "limits", "account_id", "strategy_version_id",
    ):  # fmt: skip
        op.drop_column("instances", c)
    op.drop_column("engines", "cpu_reservation")
    op.drop_column("engines", "memory_reservation_mb")
    op.execute("DROP TRIGGER strategy_versions_immutable ON strategy_versions")
    op.drop_table("strategy_versions")
    op.execute("DROP FUNCTION strategy_versions_immutable()")
    op.drop_table("strategies")
    op.drop_table("accounts")
    op.drop_table("secrets")
