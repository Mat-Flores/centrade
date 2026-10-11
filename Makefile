.PHONY: help secrets bootstrap-admin up down test lint insecure-sweep e2e-live

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

# E2E du Cockpit sur une vraie pile jetable : Postgres et Redis en conteneurs sans volume (testcontainers),
# API et worker en processus locaux avec le FakeEngine, administrateur aux identifiants aléatoires (dossier
# temporaire hors dépôt, effacé par le script). Ne touche ni à `make up` ni à la base de développement.
e2e-live: ## E2E sur pile jetable avec le FakeEngine (Docker requis)
	pnpm -C apps/web build
	@set -e; dir=$$(mktemp -d -t centrade-e2e-XXXXXX); \
	PYTHONPATH="$(CURDIR)/apps/api:$(CURDIR)/apps/worker:$(CURDIR)/packages/core:$(CURDIR)/packages/adapters/fake" \
	  uv run python scripts/e2e_stack.py --dir $$dir & pid=$$!; \
	trap 'kill $$pid 2>/dev/null; wait $$pid 2>/dev/null || true' EXIT; \
	for i in $$(seq 1 300); do [ -f $$dir/ready.json ] && break; kill -0 $$pid 2>/dev/null || { echo "pile e2e arrêtée"; exit 1; }; sleep 1; done; \
	[ -f $$dir/ready.json ] || { echo "pile e2e non prête"; exit 1; }; \
	api=$$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['api_url'])" $$dir/ready.json); \
	E2E_LIVE=1 E2E_API_URL=$$api E2E_CREDS_FILE=$$dir/creds.json pnpm -C apps/web e2e:live
