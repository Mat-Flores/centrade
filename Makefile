.PHONY: help secrets bootstrap-admin up down test lint insecure-sweep

help: ## Liste les cibles
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ :/'

# Générés une seule fois, jamais affichés. Dossier 700 ; fichiers 644 car le conteneur
# (uid 70 ou 999) doit les lire : le dossier protège contre les autres comptes de l'hôte.
secrets: secrets/postgres_password secrets/app_db_password secrets/redis.conf secrets/master_key ## Génère les secrets Docker absents

secrets/postgres_password:
	@install -d -m 700 secrets
	@umask 077 && head -c 32 /dev/urandom | base64 | tr -d '/+=\n' > $@ && chmod 644 $@

# Mot de passe du rôle Postgres applicatif (le propriétaire ne sert qu'aux migrations).
secrets/app_db_password:
	@install -d -m 700 secrets
	@umask 077 && head -c 32 /dev/urandom | base64 | tr -d '/+=\n' > $@ && chmod 644 $@

secrets/redis.conf:
	@install -d -m 700 secrets
	@umask 077 && printf 'requirepass %s\n' "$$(head -c 32 /dev/urandom | base64 | tr -d '/+=\n')" > $@ && chmod 644 $@

# Clé maître AES-256 (TOTP, puis SecretStore) : 32 octets aléatoires en base64. Cible de fichier :
# make ne la régénère jamais si elle existe. La perdre rend les secrets chiffrés illisibles.
secrets/master_key:
	@install -d -m 700 secrets
	@umask 077 && head -c 32 /dev/urandom | base64 > $@ && chmod 644 $@

# Compose cherche `.env` à côté du fichier Compose, pas à la racine : on le lui désigne.
COMPOSE = docker compose $(if $(wildcard .env),--env-file .env) -f deploy/compose/core.yml --profile core

up: secrets ## Démarre le profil core (reconstruit les images)
	$(COMPOSE) up -d --wait --build

down: ## Arrête le profil core (jamais -v)
	$(COMPOSE) down

# Sur l'hôte. `run` lance un conteneur neuf de l'API (terminal interactif), après migrate. Mot de passe saisi sans écho ; URI TOTP et codes de récupération
# affichés une seule fois. Refuse s'il existe déjà un administrateur (SPEC §13).
bootstrap-admin: ## Crée le premier administrateur
	$(COMPOSE) run --rm api python -m centrade_api.auth.bootstrap

test: ## Tests Python et front
	uv run pytest
	pnpm -C apps/web test

insecure-sweep: ## Candidats de valeurs par défaut non sûres (repli de insecure-defaults:audit)
	uv run python scripts/insecure_defaults_sweep.py $(or $(SCOPE),apps deploy scripts Makefile .env.example .github)

lint: ## ruff, mypy, ESLint, tsc
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	pnpm -C apps/web lint
	pnpm -C apps/web typecheck
