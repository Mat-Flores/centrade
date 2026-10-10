# Tâches — Jalon M0

## Critères d'acceptation (SPEC §14)

- [x] C1 `docker compose up` démarre — preuve : `make up`, `docker compose ps` tous `healthy`, `curl` de la santé de l'API et de la page de login
- [x] C2 CI verte — preuve : `gh run view` (push de `jalon/m0` à autoriser par l'opérateur)
- [x] C3 Page de login — preuve : test Playwright + capture
- [ ] C4 `/doctor` sans alerte — à confirmer par l'opérateur
- [x] C5 gitleaks vert — preuve : `gitleaks git` sur tout l'historique, par l'image épinglée de la CI (le hook pre-commit ne regarde que ce qui est indexé)
- [x] C6 Modèle de menaces rédigé — preuve : `docs/security/threat-model.md`, relu par l'auditeur de sécurité
- [x] C7 Jetons de design en place — preuve : fichier de jetons, `npx impeccable detect apps/web/src` sans constat primaire
- [x] C8 Chaque invariant a ses tests prévus et son jalon — preuve : `docs/invariants.md` + `tests/invariants/test_registre.py`

## Contenu du jalon

- [x] `CLAUDE.md` et `.claude/` vérifiés (rapport `Explore`)
- [x] Lot A — socle Python, `apps/api`, Makefile, `.env.example`
- [x] Lot D — CI, Dependabot, pre-commit (gitleaks, ruff), semgrep
- [x] Lot E — README, threat-model, accepted-risks, invariants.md, docs/agentic
- [x] `PRODUCT.md` — opérateur : `/impeccable init`
- [x] Lot B — `apps/web` : jetons, login, gates frontend
- [x] Lot C — Compose `core`, Dockerfiles, Caddy
- [x] `DESIGN.md` — opérateur : `/impeccable document`

## Points de contrôle

- [x] Après la vague 1 : `uv run ruff check .`, `uv run mypy`, `uv run pytest` verts
- [x] Après la vague 2 : `make lint test` vert (agent `test-runner`), `make up` sain
- [x] Revues indépendantes : `agent-skills:security-auditor`, `agent-skills:code-reviewer`, revue d'interface ; aucun constat critique ou élevé ouvert
- [x] Vérification des skills déclenchés, mise à jour du threat-model, `docs/agentic/couts.md`
