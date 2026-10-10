# Centrade

Plateforme de trading centralisée : une **façade de gouvernance** au-dessus d'un moteur de trading existant (Freqtrade en V1). Elle règle le moteur, le borne, le surveille et montre ce qu'il fait réellement. Elle **ne décide d'aucun trade et n'émet aucun ordre** (SPEC §1, I11).

> Ce logiciel n'est pas un conseil financier. On construit l'infrastructure, pas une stratégie « rentable ». L'utilisateur assume les risques du trading.

## Prérequis

Linux, macOS ou Windows avec WSL2 ; Docker et Docker Compose ; `uv` ; Node 22+ et `pnpm` ; `make` (SPEC §15). Aucune clé live n'est nécessaire ni admise en développement.

## Démarrage

```
uv run pre-commit install   # une fois : gitleaks et ruff avant chaque commit
cp .env.example .env     # valeurs de développement, aucun secret réel
make up                  # Compose core : Postgres/Timescale, Redis, API, web, Caddy
make down                # arrêt, volumes conservés
make lint
make test
```

Caddy n'écoute que sur `127.0.0.1`. Le contrat exact des cibles est dans `docs/decisions/0001-ossature-m0.md`.

## Architecture en bref

Dashboard web et API du plan de contrôle derrière Caddy ; PostgreSQL/TimescaleDB et Redis pour les données et le bus. Les jalons suivants ajoutent Risk service, worker, adaptateurs, moteurs, n8n et agents, sur des réseaux Docker séparés (SPEC §3, §13). Tout démarre en paper ; le live ne s'active que par la procédure de promotion (F1).

## État d'avancement

**M0 (ossature).** Dépôt, Compose `core`, CI, page de login, jetons de design, documents de sécurité. **Pas d'authentification avant M1** : la page de login n'ouvre aucun accès. Aucun invariant ni scénario n'est encore testé ; ils sont planifiés dans `docs/invariants.md`.

## Hypothèses du SPEC §15 appliquées

Crypto via Freqtrade, spot uniquement, paper ou testnet par défaut ; un seul opérateur ; VPS Linux (4 vCPU, 8 Go minimum) ; interface en français, fuseau America/Toronto ; rien exposé à Internet, accès par VPN ; jour de risque 00:00 UTC, nombres `fr-CA`.

## Où trouver le reste

- `SPEC.md` : source de vérité (invariants §1.2, jalons §14).
- `docs/invariants.md` : invariants et scénarios, tests prévus.
- `docs/security/` : modèle de menaces, risques acceptés.
- `docs/decisions/` : ADR. `docs/agentic/` : protocole de jalon, coûts.
- `CLAUDE.md` et `.claude/` : environnement agentique, fournis par l'opérateur.
