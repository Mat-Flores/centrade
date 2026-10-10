# Plan — Jalon M0 (ossature)

Source : SPEC.md §14 ligne M0, §5, §9, §13, §16, §17, annexe A. Branche `jalon/m0`.

## Ce que M0 livre

Un dépôt qui démarre (`make up`), une CI, une page de login sans authentification derrière (l'auth est à M1), les jetons de design, le modèle de menaces et `docs/invariants.md`. Aucun invariant ni scénario n'est testé à M0 : ils sont seulement planifiés (critère « chaque invariant a ses tests prévus et son jalon »).

## Décisions

- **Contrat du Makefile** (fixé ici pour paralléliser) : `make lint` = `uv run ruff check .` + `uv run ruff format --check .` + `uv run mypy` + `pnpm -C apps/web lint` + `pnpm -C apps/web typecheck` ; `make test` = `uv run pytest` + `pnpm -C apps/web test` ; `make up` / `make down` = `docker compose -f deploy/compose/core.yml --profile core up -d --wait` / `down` (jamais `-v`).
- **Contrat du front** : `apps/web/package.json` (champ `packageManager`), `pnpm-lock.yaml`, `.node-version`, scripts `lint`, `typecheck`, `test`, `build`, `e2e` (Playwright + axe). Dockerfiles : `apps/api/Dockerfile`, `apps/web/Dockerfile`.
- **API à M0** : une seule route, `GET /api/v1/system/health` (vivacité). Pas de SQLAlchemy, d'Alembic ni de client Redis avant M1 : aucune table n'existe, et l'API n'affiche pas un état de base qu'elle n'observe pas (I1). La santé de Postgres et Redis est portée par les healthchecks Compose.
- **Login à M0** : formulaire qui poste sur `/api/v1/auth/login` ; toute réponse non 2xx affiche l'état d'erreur. Aucun faux succès.
- **Image web** : build Vite, fichiers statiques servis par la même image Caddy épinglée (pas de nouvelle image). Caddy frontal séparé (réseau `edge`).
- **Exposition en dev** : Caddy lié à `127.0.0.1` (§13 : rien sur Internet ; l'interface VPN est une valeur d'environnement en production).
- **Outils absents du poste** (gitleaks, pre-commit, semgrep) : `pre-commit` en dépendance de dev (`uv run pre-commit`), gitleaks par son hook pre-commit, semgrep en CI.
- **Répertoires de l'annexe A** : créés quand un jalon y met du code ; M0 crée `apps/api`, `apps/web`, `deploy/`, `docs/`, `tests/invariants/`.
- Les agents ne committent pas : l'orchestrateur committe un lot à la fois.

## Lots

| Lot | Contenu | Dépend de | Modèle |
| --- | --- | --- | --- |
| A | Socle Python (uv, ruff, mypy, pytest), `apps/api`, Makefile, `.env.example` | — | sonnet |
| D | CI GitHub Actions, Dependabot, pre-commit, gitleaks, semgrep | contrat du Makefile | sonnet |
| E | README, threat-model, accepted-risks, invariants.md, docs/agentic, test du registre d'invariants | — | sonnet |
| B | `apps/web` : jetons de design, page de login, ESLint, tsc, Playwright + axe | `PRODUCT.md` (opérateur : `/impeccable init`) | sonnet |
| C | `deploy/compose/core.yml`, Dockerfiles, Caddy, secrets Docker | A, B | sonnet |

Vague 1 : A, D, E en parallèle. Vague 2 : B puis C. Ensuite : gate, revues indépendantes, `DESIGN.md` (opérateur : `/impeccable document`), vérification, clôture.

## Risques

| Risque | Effet | Parade |
| --- | --- | --- |
| Context7 non authentifié dans la session | Pas de doc par MCP | `agent-skills:source-driven-development` sur la doc officielle et les registres ; à autoriser par l'opérateur |
| `gh` absent, pas d'autorisation de push | « CI verte » non prouvable | Mêmes contrôles en local ; critère « à confirmer par l'opérateur » |
| `frontend-design` et `chrome-devtools-mcp` désactivés à M0 alors que le tableau des déclencheurs les cite pour un écran | Skills indisponibles | Ligne M0 du tableau des plugins appliquée (`impeccable`, `shadcn`) ; vérification par Playwright + axe ; écart signalé à l'opérateur |
| Tags et digests d'images codés de mémoire | Build cassé ou image non voulue | Chaque tag et digest est relu sur le registre avant d'être écrit |
