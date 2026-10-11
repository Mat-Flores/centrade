# Tâches — Jalon M1

## Critères d'acceptation (SPEC §14)

- [ ] C1 Instances simulées visibles en temps réel — preuve : test E2E Playwright sur FakeEngine + capture
- [ ] C2 Audit alimenté — preuve : tests I14, `GET /audit` après un parcours
- [ ] C3 Tests de propriétés sur l'idempotence des événements — preuve : test Hypothesis vert
- [ ] C4 Captures de référence du Cockpit — preuve : `docs/captures/m1/` (clair, sombre ; 1280 px, tablette)
- [ ] C5 I1 testé — `tests/invariants/test_i01_verite_affichage.py`
- [ ] C6 I8 testé — `tests/invariants/test_i08_*.py`
- [ ] C7 I14 testé — `tests/invariants/test_i14_*.py`
- [ ] C8 S9 vert — `tests/scenarios/test_s09_evenements_degrades.py`
- [ ] C9 S10 vert — `tests/scenarios/test_s10_commande_sans_reponse.py`
- [ ] C10 Masquage des secrets dans les logs — `test_i12_logs_masquent_les_valeurs_sentinelles`
- [ ] C11 Gates du §0.8 : `make lint test` vert, migrations, `docker compose up` sain, CI verte (push à autoriser)

## Lots

- [ ] Lot A — socle de données, audit, masquage des logs
  - Acceptation : `alembic upgrade head` sur une base vide ; `events` est une hypertable ; UPDATE et DELETE sur `audit_log` refusés ; `test_i14_journal_d_audit_inalterable` et `test_i12_logs_masquent_les_valeurs_sentinelles` verts
- [ ] Lot F — contrat moteur, événements canoniques, FakeEngine
  - Acceptation : suite de conformité verte sur FakeEngine ; les dix modes de panne activables ; décimaux en chaînes dans l'enveloppe
- [ ] Lot B — auth, 2FA, RBAC
  - Acceptation : pas de session sans TOTP ; rôle insuffisant = 403 ; échecs journalisés et verrouillage progressif ; `make bootstrap-admin` crée le premier admin
- [ ] Lot C — bus, ingestion, projections, worker
  - Acceptation : S9 vert ; propriété « rejouer, dupliquer ou permuter les événements ne change pas les projections » verte
- [ ] Lot E — coquille du front, étape TOTP
  - Acceptation : login en deux étapes ; barre persistante ; `pnpm lint`, `tsc`, `pnpm test`, `npx impeccable detect apps/web/src` verts
- [ ] Lot D — instances, commandes, SSE
  - Acceptation : I1 et I8 verts ; S10 vert ; chaque commande écrit une ligne d'audit avec son auteur ; worker sain dans Compose
- [ ] Lot G — Cockpit
  - Acceptation : instance créée visible sans rechargement ; valeur périmée estompée et marquée ; commande `timed_out` visible, jamais « fait » ; axe sans violation sérieuse ; captures

## Points de contrôle

- [ ] Après la vague 1 (A, F) : `uv run ruff check .`, `uv run mypy`, `uv run pytest` verts
- [ ] Après la vague 2 (B, C, E) : `make lint test` vert
- [ ] Après la vague 3 (D) : `make up` sain, parcours login → instance → commande à la main
- [ ] Après la vague 4 (G) : `make lint test` vert (agent `test-runner`), E2E verts
- [ ] Revues indépendantes : sécurité, code, interface ; aucun constat critique ou élevé ouvert
- [ ] Vérification des skills déclenchés, `docs/invariants.md`, threat-model, README (hypothèses), `docs/agentic/couts.md`
