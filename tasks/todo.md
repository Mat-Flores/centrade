# Tâches — Jalon M0

## Critères d'acceptation (SPEC §14)

- [ ] C1 `docker compose up` démarre — preuve : `make up`, `docker compose ps` tous `healthy`, `curl` de la santé de l'API et de la page de login
- [ ] C2 CI verte — preuve : `gh run view` (push de `jalon/m0` à autoriser par l'opérateur)
- [ ] C3 Page de login — preuve : test Playwright + capture
- [ ] C4 `/doctor` sans alerte — à confirmer par l'opérateur
- [ ] C5 gitleaks vert — preuve : `uv run pre-commit run gitleaks --all-files`
- [ ] C6 Modèle de menaces rédigé — preuve : `docs/security/threat-model.md`, relu par l'auditeur de sécurité
- [ ] C7 Jetons de design en place — preuve : fichier de jetons, `npx impeccable detect apps/web/src` sans constat primaire
- [ ] C8 Chaque invariant a ses tests prévus et son jalon — preuve : `docs/invariants.md` + `tests/invariants/test_registre.py`

## Contenu du jalon

- [x] `CLAUDE.md` et `.claude/` vérifiés (rapport `Explore`)
- [ ] Lot A — socle Python, `apps/api`, Makefile, `.env.example`
- [ ] Lot D — CI, Dependabot, pre-commit (gitleaks, ruff), semgrep
- [ ] Lot E — README, threat-model, accepted-risks, invariants.md, docs/agentic
- [ ] `PRODUCT.md` — opérateur : `/impeccable init`
- [ ] Lot B — `apps/web` : jetons, login, gates frontend
- [ ] Lot C — Compose `core`, Dockerfiles, Caddy
- [ ] `DESIGN.md` — opérateur : `/impeccable document`

## Points de contrôle

- [ ] Après la vague 1 : `uv run ruff check .`, `uv run mypy`, `uv run pytest` verts
- [ ] Après la vague 2 : `make lint test` vert (agent `test-runner`), `make up` sain
- [ ] Revues indépendantes : `agent-skills:security-auditor`, `agent-skills:code-reviewer`, revue d'interface ; aucun constat critique ou élevé ouvert
- [ ] Vérification des skills déclenchés, mise à jour du threat-model, `docs/agentic/couts.md`
