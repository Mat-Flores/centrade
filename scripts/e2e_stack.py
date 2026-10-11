"""Pile jetable pour `make e2e-live` : Postgres/Timescale et Redis (testcontainers), migrations, un
administrateur aux identifiants aléatoires, l'API et le worker en processus locaux (FakeEngine).

Rien n'est persistant : conteneurs sans volume, secrets et identifiants dans un dossier temporaire
(hors du dépôt, mode 700) effacé à l'arrêt. Aucune clé de venue, aucun ordre réel : le seul moteur
est le FakeEngine. Écrit `ready.json` et `creds.json` dans `--dir` quand tout répond, puis attend
SIGTERM ou SIGINT.

    uv run python scripts/e2e_stack.py --dir "$(mktemp -d -t centrade-e2e-XXXXXX)"
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from alembic import command
from alembic.config import Config
from centrade_api.auth.bootstrap import create_first_admin
from centrade_core.db import make_engine, make_session_factory
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

ROOT = Path(__file__).resolve().parents[1]
PYTHONPATH = ":".join(
    str(ROOT / p) for p in ("apps/api", "apps/worker", "packages/core", "packages/adapters/fake")
)
# Origine publique attendue par l'API (CSRF) ; le relais Vite la présente à la place de celle du
# navigateur.
PUBLIC_ORIGIN = "https://localhost:8443"


def compose_image(prefix: str) -> str:
    compose = (ROOT / "deploy" / "compose" / "core.yml").read_text(encoding="utf-8")
    found = re.search(rf"^\s*image:\s*({re.escape(prefix)}\S+)", compose, re.M)
    if not found:
        raise SystemExit(f"image {prefix} absente de core.yml")
    return found.group(1)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_health(url: str, timeout_s: float = 60) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310 - 127.0.0.1 local
                if json.load(response)["status"] == "ok":
                    return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.5)
    raise SystemExit("l'API ou le worker n'est pas devenu sain à temps")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        help="dossier temporaire créé par l'appelant, effacé à l'arrêt",
    )
    args = parser.parse_args()
    # Garde-fou : on n'efface qu'un sous-dossier du dossier temporaire du système, jamais le dépôt.
    shared = args.dir.resolve()
    if shared.parent != Path(tempfile.gettempdir()).resolve() or not shared.name.startswith(
        "centrade-e2e-"
    ):
        raise SystemExit(
            "--dir doit être un dossier centrade-e2e-* du dossier temporaire du système"
        )
    args.ready_file = shared / "ready.json"
    args.creds_file = shared / "creds.json"

    stop = False

    def request_stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    work = Path(tempfile.mkdtemp(prefix="centrade-e2e-"))
    work.chmod(0o700)
    procs: list[subprocess.Popen[bytes]] = []

    def stop_procs() -> None:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        procs.clear()

    try:
        db_password = secrets.token_urlsafe(24)
        pg = PostgresContainer(
            compose_image("timescale/timescaledb"),
            driver="asyncpg",
            username="centrade",
            password=db_password,
            dbname="centrade",
        )
        with pg, RedisContainer(compose_image("redis:")) as redis:
            db_url = pg.get_connection_url()
            parts = urlsplit(db_url)
            redis_url = (
                f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(redis.port)}/0"
            )

            (work / "postgres_password").write_text(db_password, encoding="utf-8")
            master_key = secrets.token_bytes(32)
            (work / "master_key").write_text(
                base64.b64encode(master_key).decode(), encoding="utf-8"
            )
            api_port = free_port()
            env = {
                **os.environ,
                "PYTHONPATH": PYTHONPATH,
                "CENTRADE_DB_HOST": parts.hostname or "127.0.0.1",
                "CENTRADE_DB_PORT": str(parts.port),
                "CENTRADE_DB_USER": "centrade",
                "CENTRADE_DB_NAME": "centrade",
                "CENTRADE_POSTGRES_PASSWORD_FILE": str(work / "postgres_password"),
                "CENTRADE_MASTER_KEY_FILE": str(work / "master_key"),
                "CENTRADE_REDIS_URL": redis_url,
                "CENTRADE_PUBLIC_ORIGIN": PUBLIC_ORIGIN,
                "CENTRADE_WORKER_INTERVAL_S": "0.5",
                # Pile jetable seulement : les E2E simulent des pannes du FakeEngine.
                "CENTRADE_ENGINE_FAILURE_INJECTION": "true",
            }
            os.environ.update({k: v for k, v in env.items() if k.startswith("CENTRADE_")})

            cfg = Config(str(ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(ROOT / "packages" / "core" / "alembic"))
            cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
            command.upgrade(cfg, "head")

            # Identifiants propres à cette exécution ; jamais écrits dans le dépôt ni affichés.
            email = f"e2e-{secrets.token_hex(4)}@example.test"
            password = secrets.token_urlsafe(24)

            async def make_admin() -> str:
                engine = make_engine(db_url)
                try:
                    created = await create_first_admin(
                        make_session_factory(engine), master_key, email=email, password=password
                    )
                finally:
                    await engine.dispose()
                return parse_qs(urlsplit(created.totp_uri).query)["secret"][0]

            totp_secret = asyncio.run(make_admin())
            args.creds_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(args.creds_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"email": email, "password": password, "totp_secret": totp_secret}, f)

            try:
                procs.append(
                    subprocess.Popen(  # noqa: S603 - arguments fixes, aucune entrée externe
                        [
                            sys.executable,
                            "-m",
                            "uvicorn",
                            "centrade_api.main:app",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            str(api_port),
                        ],
                        env=env,
                    )
                )
                procs.append(subprocess.Popen([sys.executable, "-m", "centrade_worker"], env=env))
                api_url = f"http://127.0.0.1:{api_port}"
                wait_health(f"{api_url}/api/v1/system/health")

                args.ready_file.write_text(
                    json.dumps({"api_url": api_url, "public_origin": PUBLIC_ORIGIN}),
                    encoding="utf-8",
                )
                print("pile e2e prête", flush=True)
                while not stop and all(p.poll() is None for p in procs):
                    time.sleep(0.5)
            finally:
                stop_procs()  # avant les conteneurs : pas d'erreurs de connexion à l'arrêt
    finally:
        stop_procs()
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(shared, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
