# ADR-0004 : Dépendances du jalon M1

## Statut
Acceptée

## Date
2026-10-10

## Contexte
M1 ajoute la base applicative, l'authentification, le bus et les tests d'intégration (SPEC §14). Le SPEC §5 impose SQLAlchemy 2 async, Alembic, Redis Streams, argon2id, TOTP, AES-256-GCM, Hypothesis et testcontainers ; il ne nomme pas les bibliothèques. Les versions exactes sont figées par `uv.lock`.

## Décision

| Paquet | Version | Rôle | Hors §5 ? |
| --- | --- | --- | --- |
| `sqlalchemy[asyncio]` | 2.1.4 | ORM async (inclut `greenlet`) | non |
| `asyncpg` | 0.32.0 | pilote Postgres async de SQLAlchemy | oui : pilote exigé par `postgresql+asyncpg` |
| `alembic` | 1.20.0 | migrations | non |
| `redis` | 8.1.0 | client Redis Streams (asyncio inclus) | oui : client du bus du §5 |
| `pydantic-settings` | 2.15.0 | configuration, secrets lus dans des fichiers | oui : même éditeur que Pydantic, déjà imposé |
| `argon2-cffi` | 25.1.0 | hachage argon2id | oui : implémentation de référence de l'algorithme du §5 |
| `pyotp` | 2.10.0 | TOTP (RFC 6238) | oui : évite d'écrire de la cryptographie |
| `cryptography` | 50.0.2 | AES-256-GCM du `SecretStore` et du secret TOTP | oui : bibliothèque standard de fait |
| dev : `hypothesis` | 6.168.5 | tests de propriétés (§5) | non |
| dev : `testcontainers[postgres,redis]` | 4.15.0 | Postgres/TimescaleDB et Redis réels en test | non |
| dev : `pytest-asyncio` | 1.4.0 | tests `async` | oui : pytest ne les exécute pas seul |

Aucun ORM de remplacement, aucun client Redis synchrone, aucun paquet de hachage maison.

## Audit de chaîne d'approvisionnement
Collecteur `supply-chain-risk-auditor` lancé sur `pyproject.toml` et `uv.lock`, le 2026-10-10 : 20 dépendances directes, 45 transitives vérifiées.
- Aucun avis de sécurité connu, direct ou transitif, aux versions verrouillées. Aucune dépendance obsolète, retirée ou archivée.
- Non évaluable (PyPI ne le publie pas) : concentration des éditeurs, scripts d'installation, provenance de publication, volumes de téléchargement. Absence de constat n'est donc pas une garantie sur ces points.
- Scorecard OpenSSF indisponible pour `asyncpg`, `pydantic-settings`, `hypothesis`, `fastapi`, `uvicorn`, `ruff`.
- Pas de politique de sécurité publiée : `asyncpg`, `cryptography`, `redis`, `hypothesis`, `pytest-asyncio`, `testcontainers`.
À refaire à chaque montée de version, et en CI avec `pip-audit` (§5).

## Limites connues
- `testcontainers` pilote Docker : les tests d'intégration exigent un démon Docker local (absent = échec, pas de saut silencieux).
- `asyncpg` exécute une seule commande SQL par appel : les migrations Alembic séparent leurs instructions.

## Alternatives écartées
- `psycopg` 3 : un second pilote à maintenir sans bénéfice ici.
- `passlib`, `bcrypt` : le §5 impose argon2id.
- `python-jose`/PyJWT : les sessions sont des cookies opaques côté serveur, pas des JWT.

## Conséquences
- `pyproject.toml` n'est modifié que par le lot A pendant la vague 1 de M1.
- L'ADR 0001 (point « limites connues ») est soldée pour les journaux d'uvicorn : ils passent par structlog et le masquage de `centrade_core.logging`.
