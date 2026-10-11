# Centrade

Plateforme de trading centralisée : une **façade de gouvernance** au-dessus d'un moteur de trading existant (Freqtrade en V1). Elle règle le moteur, le borne, le surveille et montre ce qu'il fait réellement. Elle **ne décide d'aucun trade et n'émet aucun ordre** (SPEC §1, I11).

> Ce logiciel n'est pas un conseil financier. On construit l'infrastructure, pas une stratégie « rentable ». L'utilisateur assume les risques du trading.

## Prérequis

Linux, macOS ou Windows avec WSL2 ; Docker et Docker Compose ; `uv` ; Node 22+ et `pnpm` ; `make` (SPEC §15). Aucune clé live n'est nécessaire ni admise en développement.

## Démarrage

```
uv run pre-commit install   # une fois : gitleaks et ruff avant chaque commit
cp .env.example .env     # valeurs de développement, aucun secret réel
make secrets             # génère les secrets Docker absents
make up                  # Compose core : Postgres/Timescale, Redis, API, worker, web, Caddy
make bootstrap-admin     # premier administrateur ; terminal interactif, aucun identifiant par défaut
make down                # arrêt, volumes conservés
make lint test
pnpm e2e                 # dans apps/web : E2E du Cockpit
make e2e-live            # pile jetable avec le moteur simulé ; local seulement, pas en CI
```

**Avertissement.** La sortie de `make bootstrap-admin` contient l'URI TOTP et les codes de récupération. Note-les hors ligne et ne les laisse dans aucun journal (le pilote de journaux Docker garde la sortie du conteneur).

**Installation venant de M0.** Fais `make down` puis `make up` : le réseau `edge` passe en `172.31.250.0/24`, qui doit être libre sur l'hôte.

L'interface est sur `https://localhost:8443` (le certificat interne est émis pour `localhost`, pas pour `127.0.0.1` ; certificat de l'autorité interne de Caddy : le navigateur avertit tant qu'elle n'est pas approuvée). Caddy n'écoute que sur `127.0.0.1` ; l'adresse, le port et le nom d'hôte se règlent dans `.env`, à la racine. Le contrat exact des cibles est dans `docs/decisions/0001-ossature-m0.md`.

## Architecture en bref

Dashboard web et API du plan de contrôle derrière Caddy ; PostgreSQL/TimescaleDB et Redis pour les données et le bus. Les jalons suivants ajoutent Risk service, worker, adaptateurs, moteurs, n8n et agents, sur des réseaux Docker séparés (SPEC §3, §13). Tout démarre en paper ; le live ne s'active que par la procédure de promotion (F1).

## État d'avancement

**M0 (ossature).** Dépôt, Compose `core`, CI, page de login, jetons de design, documents de sécurité.

**M1 livré.** Authentification et 2FA, contrat moteur, moteur simulé et ses modes de panne, bus, commandes suivies jusqu'à l'effet, Cockpit en temps réel. Testés : I1, I8, I14, S9, S10 (I4, I5 et I12 en partie) ; le reste est planifié dans `docs/invariants.md`.

## Hypothèses du SPEC §15 appliquées

Crypto via Freqtrade, spot uniquement, paper ou testnet par défaut ; un seul opérateur ; VPS Linux (4 vCPU, 8 Go minimum) ; interface en français, fuseau America/Toronto ; rien exposé à Internet, accès par VPN ; jour de risque 00:00 UTC, nombres `fr-CA`.

**Hypothèses de M1.**
- Le worker existe dès M1 et porte le moteur simulé en mémoire : une instance simulée est redéployée en sorties seules à chaque démarrage du worker.
- Le secret TOTP est chiffré par AES-256-GCM avec la clé maître ; l'interface SecretStore complète arrive à M2.
- Le kill switch est visible mais désactivé jusqu'à M3.
- Le Cockpit n'affiche ni PnL, ni exposition, ni drawdown, ni rejets de risque, ni panneau « Garanties » tant que leurs sources n'existent pas (M2 à M4).
- Pas de routeur côté front tant qu'un seul écran est actif.
- Écarts acceptés : `docs/decisions/0006-ecarts-m1.md`.

## Où trouver le reste

- `SPEC.md` : source de vérité (invariants §1.2, jalons §14).
- `docs/invariants.md` : invariants et scénarios, tests prévus.
- `docs/security/` : modèle de menaces, risques acceptés.
- `docs/decisions/` : ADR. `docs/agentic/` : protocole de jalon, coûts.
- `CLAUDE.md` et `.claude/` : environnement agentique, fournis par l'opérateur.
