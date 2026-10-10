.PHONY: help up down test lint

help: ## Liste les cibles
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ :/'

up: ## Démarre le profil core
	docker compose -f deploy/compose/core.yml --profile core up -d --wait

down: ## Arrête le profil core (jamais -v)
	docker compose -f deploy/compose/core.yml --profile core down

test: ## Tests Python et front
	uv run pytest
	pnpm -C apps/web test

lint: ## ruff, mypy, ESLint, tsc
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	pnpm -C apps/web lint
	pnpm -C apps/web typecheck
