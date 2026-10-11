"""Tables de M1 : utilisateurs, sessions, moteurs, instances, commandes, événements, audit.

Revision ID: 0001
Revises:
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
NUM = sa.Numeric(38, 18)
NOW = sa.text("now()")


def _id() -> sa.Column[Any]:
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True)


def _uuid(name: str, **kw: Any) -> sa.Column[Any]:
    return sa.Column(name, pg.UUID(as_uuid=True), **kw)


def _in(col: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{col} IN ({', '.join(repr(v) for v in values)})", name=name)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "users",
        _id(),
        sa.Column("username", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("totp_secret_enc", sa.LargeBinary),
        sa.Column("totp_nonce", sa.LargeBinary),
        sa.Column("recovery_code_hashes", pg.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("failed_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", TS),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.UniqueConstraint("username", name="uq_users_username"),
        _in("role", ("viewer", "operator", "admin"), "role"),
    )
    op.create_table(
        "sessions",
        _id(),
        _uuid("user_id", nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("last_activity_at", TS, nullable=False, server_default=NOW),
        sa.Column("expires_at", TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        _in("stage", ("pre_totp", "full"), "stage"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "engines",
        _id(),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("image", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("digest", sa.Text),
        sa.Column("capabilities", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
    )
    op.create_table(
        "instances",
        _id(),
        _uuid("engine_id", nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("desired_state", sa.Text, nullable=False),
        sa.Column("observed_state", sa.Text, nullable=False, server_default="unknown"),
        sa.Column("observed_at", TS),
        sa.Column("observed_mode", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["engine_id"], ["engines.id"], name="fk_instances_engine_id_engines"
        ),
        sa.UniqueConstraint("name", name="uq_instances_name"),
        _in("mode", ("paper", "live"), "mode"),
        _in("desired_state", ("running", "exits_only", "stopped"), "desired_state"),
        _in(
            "observed_state",
            ("starting", "exits_only", "running", "halted", "stopped", "error", "unknown"),
            "observed_state",
        ),
        _in("observed_mode", ("paper", "live"), "observed_mode"),
    )
    op.create_index("ix_instances_engine_id", "instances", ["engine_id"])
    # Le mode d'une instance ne change jamais (I3) : on en crée une autre.
    # asyncpg n'accepte qu'une commande par appel : un op.execute par instruction.
    op.execute("""
        CREATE FUNCTION instances_mode_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.mode IS DISTINCT FROM OLD.mode THEN
                RAISE EXCEPTION 'instances.mode est immuable';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute(
        "CREATE TRIGGER instances_mode_immutable BEFORE UPDATE ON instances "
        "FOR EACH ROW EXECUTE FUNCTION instances_mode_immutable()"
    )

    op.create_table(
        "commands",
        _id(),
        _uuid("instance_id", nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="requested"),
        _uuid("correlation_id", nullable=False),
        sa.Column("deadline_at", TS, nullable=False),
        sa.Column("requested_at", TS, nullable=False, server_default=NOW),
        sa.Column("dispatched_at", TS),
        sa.Column("acknowledged_at", TS),
        sa.Column("verified_at", TS),
        sa.Column("failed_at", TS),
        sa.Column("timed_out_at", TS),
        sa.Column("superseded_at", TS),
        sa.Column("result", pg.JSONB),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["instances.id"], name="fk_commands_instance_id_instances"
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_commands_idempotency_key"),
        _in(
            "status",
            (
                "requested",
                "dispatched",
                "acknowledged",
                "verified",
                "failed",
                "timed_out",
                "superseded",
            ),
            "status",
        ),
    )
    op.create_index("ix_commands_instance_id", "commands", ["instance_id"])

    op.create_table(
        "events",
        _uuid("id", nullable=False),
        sa.Column("ts", TS, nullable=False),
        sa.Column("ts_ingest", TS, nullable=False, server_default=NOW),
        sa.Column("type", sa.Text, nullable=False),
        _uuid("instance_id", nullable=False),
        sa.Column("seq", sa.BigInteger, nullable=False),
        _uuid("correlation_id"),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.PrimaryKeyConstraint("id", "ts", name="pk_events"),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["instances.id"], name="fk_events_instance_id_instances"
        ),
        # Une hypertable n'accepte que des unicités qui contiennent la colonne de partition.
        sa.UniqueConstraint("instance_id", "seq", "ts", name="uq_events_instance_id_seq_ts"),
    )
    op.execute("SELECT create_hypertable('events', by_range('ts'))")

    op.create_table(
        "positions",
        _id(),
        _uuid("instance_id", nullable=False),
        sa.Column("instrument", sa.Text, nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("quantity", NUM, nullable=False),
        sa.Column("entry_price", NUM),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("observed_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["instances.id"], name="fk_positions_instance_id_instances"
        ),
        sa.UniqueConstraint(
            "instance_id", "instrument", "side", name="uq_positions_instance_instrument_side"
        ),
        _in("side", ("long", "short"), "side"),
    )
    op.create_index("ix_positions_instance_id", "positions", ["instance_id"])
    op.create_table(
        "orders",
        _id(),
        _uuid("instance_id", nullable=False),
        sa.Column("client_order_id", sa.Text, nullable=False),
        sa.Column("instrument", sa.Text, nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("intent", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("quantity", NUM, nullable=False),
        sa.Column("price", NUM),
        sa.Column("currency", sa.Text, nullable=False),
        _uuid("decision_id"),
        sa.Column("observed_at", TS, nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["instances.id"], name="fk_orders_instance_id_instances"
        ),
        sa.UniqueConstraint("client_order_id", name="uq_orders_client_order_id"),
        _in("side", ("buy", "sell"), "side"),
        _in("intent", ("entry", "increase", "exit", "stop"), "intent"),
    )
    op.create_index("ix_orders_instance_id", "orders", ["instance_id"])

    op.create_table(
        "alerts",
        _id(),
        sa.Column("rule", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("target_kind", sa.Text, nullable=False),
        _uuid("target_id"),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("message", sa.Text, nullable=False),
        _uuid("correlation_id"),
        sa.Column("invariant", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("acknowledged_at", TS),
        sa.Column("resolved_at", TS),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        _in("severity", ("info", "warning", "critical"), "severity"),
        _in("target_kind", ("instance", "account", "global"), "target_kind"),
        _in("status", ("open", "acknowledged", "resolved"), "status"),
    )

    op.create_table(
        "audit_log",
        _id(),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("ts", TS, nullable=False),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("before_hash", sa.Text),
        sa.Column("after_hash", sa.Text),
        sa.Column("ip", sa.Text),
        sa.Column("prev_hash", sa.Text, nullable=False),
        sa.Column("row_hash", sa.Text, nullable=False),
        sa.UniqueConstraint("seq", name="uq_audit_log_seq"),
        # Pas de fourche : deux lignes ne suivent pas la même, même si le verrou applicatif échoue.
        sa.UniqueConstraint("prev_hash", name="uq_audit_log_prev_hash"),
    )
    op.execute("""
        CREATE FUNCTION audit_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log est en ajout seul (% interdit)', TG_OP;
        END $$""")
    op.execute(
        "CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only()"
    )
    # Sans effet sur le propriétaire de la table ; utile dès qu'un rôle applicatif distinct existe.
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TABLE audit_log")
    op.execute("DROP FUNCTION audit_log_append_only()")
    for table in ("alerts", "orders", "positions", "events", "commands", "instances"):
        op.drop_table(table)
    op.execute("DROP FUNCTION instances_mode_immutable()")
    for table in ("engines", "sessions", "users"):
        op.drop_table(table)
