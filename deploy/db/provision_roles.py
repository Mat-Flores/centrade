"""Rôle applicatif Postgres, créé et réajusté à chaque `migrate` (idempotent).

Le propriétaire (`centrade`, superutilisateur de l'image) ne sert qu'aux migrations. Le rôle
applicatif n'a aucun droit DDL et aucun UPDATE, DELETE ni TRUNCATE sur `audit_log` : ces droits
manquent, en plus du trigger de la migration 0001 (I3, SPEC §13). Rejoué après les migrations,
il couvre les tables des révisions futures sans qu'on y pense.
Source : https://www.postgresql.org/docs/16/sql-grant.html
"""

import asyncio
import os
import re
from pathlib import Path

import asyncpg
from centrade_core.settings import get_settings

ROLE = os.environ["CENTRADE_APP_DB_USER"]
if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", ROLE):
    raise SystemExit("CENTRADE_APP_DB_USER invalide")
PASSWORD = Path(os.environ["CENTRADE_APP_DB_PASSWORD_FILE"]).read_text(encoding="utf-8").strip()
if not PASSWORD:
    raise SystemExit("mot de passe du rôle applicatif vide")

# ROLE est validé ci-dessus ; le mot de passe passe par format(%L), jamais par concaténation.
STATEMENTS = [
    f"""DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
        CREATE ROLE {ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
      END IF; END $$""",  # noqa: S608
    "REVOKE ALL ON DATABASE {db} FROM PUBLIC",
    f"GRANT CONNECT ON DATABASE {{db}} TO {ROLE}",
    "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
    f"GRANT USAGE ON SCHEMA public TO {ROLE}",
    f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}",
    f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}",
    f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}",
    # La table de version d'Alembic reste au propriétaire.
    f"REVOKE ALL ON alembic_version FROM {ROLE}",
    f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM {ROLE}",
]


async def main() -> None:
    cfg = get_settings()
    conn = await asyncpg.connect(
        host=cfg.db_host,
        port=cfg.db_port,
        user=cfg.db_user,
        database=cfg.db_name,
        password=cfg.postgres_password_file.read_text(encoding="utf-8").strip(),
    )
    try:
        async with conn.transaction():
            for stmt in STATEMENTS:
                await conn.execute(stmt.replace("{db}", f'"{cfg.db_name}"'))
            alter = await conn.fetchval(
                "SELECT format('ALTER ROLE %I PASSWORD %L', $1::text, $2::text)", ROLE, PASSWORD
            )
            await conn.execute(alter)
    finally:
        await conn.close()
    print(f"rôle {ROLE} prêt")


asyncio.run(main())
