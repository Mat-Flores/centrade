# ADR-0001 : Ossature du jalon M0

## Statut
Acceptée

## Date
2026-10-10

## Contexte
M0 livre un dépôt qui démarre, une CI, une page de login et les documents de sécurité (SPEC §14). L'authentification, la base applicative et le bus sont des travaux de M1. Les décisions viennent de `tasks/plan.md`.

## Décision

1. **Contrat du Makefile.** `make lint` = `uv run ruff check .` + `uv run ruff format --check .` + `uv run mypy` + `pnpm -C apps/web lint` + `pnpm -C apps/web typecheck`. `make test` = `uv run pytest` + `pnpm -C apps/web test`. `make up` / `make down` = `docker compose -f deploy/compose/core.yml --profile core up -d --wait --build` / `down`, sans l'option qui supprime les volumes, avec `--env-file .env` quand ce fichier existe. Raison : fixer l'interface pour que les lots A, D et E avancent en parallèle ; `down` ne détruit aucun volume (§17.5) ; Compose cherche `.env` à côté du fichier Compose et non à la racine ; sans `--build`, un code modifié ne serait pas reconstruit.
2. **Une seule route d'API à M0 : `GET /api/v1/system/health`** (vivacité). Ni SQLAlchemy, ni Alembic, ni client Redis avant M1. Raison : aucune table n'existe et l'API ne doit pas afficher un état de base qu'elle n'observe pas (I1) ; la santé de Postgres et de Redis est portée par les healthchecks Compose.
3. **Login à M0** : le formulaire poste sur `/api/v1/auth/login` ; toute réponse non 2xx affiche l'état d'erreur. Raison : aucun faux succès, l'authentification arrive à M1 (I1).
4. **Image web** : build Vite, fichiers statiques servis par le même Caddy que le frontal (image commune, voir ADR 0003) ; Caddy frontal séparé, réseau `edge`. Raison : pas de nouvelle image à épingler et à auditer (§13).
5. **Exposition en dev** : Caddy lié à `127.0.0.1` ; l'interface VPN est une valeur d'environnement en production. Raison : rien n'écoute sur Internet par défaut (§13, §15).
6. **Outils absents du poste** (gitleaks, pre-commit, semgrep) : `pre-commit` en dépendance de dev (`uv run pre-commit`), gitleaks par son hook pre-commit, semgrep en CI. Raison : aucune installation système à demander pour démarrer.
7. **Répertoires de l'annexe A créés à la demande** : M0 crée `apps/api`, `apps/web`, `deploy/`, `docs/`, `tests/invariants/`. Raison : pas de dossiers vides.
8. **Les agents ne committent pas** : l'orchestrateur committe un lot à la fois (§17.2). Raison : un point de contrôle unique par lot.
9. **`uvicorn` comme serveur ASGI.** Il ne figure pas au §5 ; FastAPI ne sert rien sans serveur ASGI et sa documentation le recommande. Raison : dépendance hors §5 consignée (§0.2).
10. **Secrets de développement** : `make secrets` génère les fichiers en mode 644 dans un dossier `secrets/` en 700, parce que les conteneurs les lisent sous un autre uid (70 pour Postgres, 999 pour Redis). Raison : valable sur un poste à un seul compte, où le dossier est la barrière. Pas pour un serveur : y poser des fichiers en 0400 possédés par l'uid du conteneur (durcissement de M7).

## Limites connues, à reprendre
- `tls internal` vaut aussi en production : l'installation de l'autorité interne sur les appareils de l'opérateur reste à documenter (runbooks, M7).
- Les journaux d'uvicorn ne passent pas par structlog : le masquage des secrets devra les couvrir quand l'authentification arrive (M1).
- Le client de test de Starlette annonce la dépréciation de `httpx` au profit de `httpx2` : à suivre lors d'une montée de version.

## Alternatives écartées
- Route de santé qui interroge Postgres et Redis dès M0 : voir 2.
- Faux succès de login en attendant M1 : voir 3.
- Installer gitleaks et semgrep sur le poste : voir 6.

## Conséquences
- `pre-commit` devient une dépendance de dev ; il figure au §5 (ligne « Qualité »), donc sans ADR propre.
- La page de login de M0 ne mène nulle part ; M1 ajoute authentification, ORM et bus.
- Le contrat du Makefile s'impose aux lots A et D.
