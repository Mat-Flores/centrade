"""First administrator, created from the host: `make bootstrap-admin` (SPEC §13).

No default credentials. The password is entered without echo; the TOTP URI and the recovery
codes are displayed only here, once: the database keeps only unreadable forms of them.
"""

import asyncio
import getpass
import sys
from dataclasses import dataclass

from centrade_core.audit import write_audit
from centrade_core.db import make_engine, make_session_factory
from centrade_core.ids import uuid7
from centrade_core.models import User
from centrade_core.settings import get_settings
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from centrade_api.auth import security

MIN_PASSWORD_LENGTH = 12


class AdminExistsError(Exception):
    pass


@dataclass(frozen=True)
class CreatedAdmin:
    totp_uri: str
    recovery_codes: list[str]


async def create_first_admin(
    session_factory: async_sessionmaker[AsyncSession],
    master_key: bytes,
    *,
    email: str,
    password: str,
) -> CreatedAdmin:
    email = email.strip().lower()
    if "@" not in email.strip("@") or len(email) > 254 or any(c.isspace() for c in email):
        raise ValueError("Adresse e-mail invalide.")
    if not MIN_PASSWORD_LENGTH <= len(password) <= 1024:
        raise ValueError(f"Le mot de passe doit compter au moins {MIN_PASSWORD_LENGTH} caractères.")
    user_id = uuid7()
    secret = security.new_totp_secret()
    codes = security.new_recovery_codes()
    nonce, encrypted = security.encrypt_totp_secret(
        master_key=master_key, user_id=user_id, secret=secret
    )
    password_hash = security.hash_password(password)
    async with session_factory() as s, s.begin():
        # Two simultaneous launches do not create two administrators.
        await s.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
        if (await s.execute(select(User.id).where(User.role == "admin").limit(1))).first():
            raise AdminExistsError
        s.add(
            User(
                id=user_id,
                username=email,
                role="admin",
                password_hash=password_hash,
                totp_secret_enc=encrypted,
                totp_nonce=nonce,
                recovery_code_hashes=[security.recovery_code_hash(c) for c in codes],
            )
        )
        await s.flush()
        await write_audit(
            s,
            actor="host:bootstrap-admin",
            action="auth.admin.created",
            target=f"user:{user_id}",
            after={"username": email, "role": "admin"},
        )
    return CreatedAdmin(totp_uri=security.totp_uri(secret, email), recovery_codes=codes)


async def _run(email: str, password: str) -> CreatedAdmin:
    settings = get_settings()
    engine = make_engine(settings.database_url())
    try:
        return await create_first_admin(
            make_session_factory(engine), settings.master_key(), email=email, password=password
        )
    finally:
        await engine.dispose()


def main() -> int:
    email = input("Adresse e-mail de l'administrateur : ")
    password = getpass.getpass("Mot de passe (12 caractères au moins) : ")
    if password != getpass.getpass("Mot de passe, à nouveau : "):
        print("Les deux saisies diffèrent. Rien n'a été créé.", file=sys.stderr)
        return 1
    try:
        created = asyncio.run(_run(email, password))
    except AdminExistsError:
        print("Un administrateur existe déjà. Rien n'a été créé.", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"{error} Rien n'a été créé.", file=sys.stderr)
        return 1
    print("\nAdministrateur créé. Ces valeurs ne seront plus jamais affichées.\n")
    print("À saisir dans l'application TOTP :")
    print(f"  {created.totp_uri}\n")
    print("Codes de récupération, à usage unique, à conserver hors ligne :")
    for code in created.recovery_codes:
        print(f"  {code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
