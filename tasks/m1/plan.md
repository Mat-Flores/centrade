# Plan — Jalon M1

Source : SPEC §14 (ligne M1), §4 F9, §6, §7, §8, §9, §13. Tâches et preuves : `tasks/m1/todo.md`.

## Ce que M1 livre

Un opérateur se connecte (mot de passe + TOTP), voit dans le Cockpit des instances simulées par le FakeEngine, en temps réel, avec l'état voulu et l'état observé daté. Chaque action est une commande suivie jusqu'à son effet, et chaque changement d'état est dans le journal d'audit.

## Décisions

- **Disposition** (annexe A) : `packages/core/centrade_core/`, `packages/adapters/fake/centrade_fake/`, `apps/worker/centrade_worker/`, à côté de `apps/api/centrade_api/`. Projet uv unique (`package = false`) : les dossiers sont ajoutés à `pythonpath` (pytest), `mypy_path` et aux images.
- **Dépôt des modèles** : tables et migrations Alembic dans `packages/core` (l'API et le worker les partagent).
- **Worker dès M1** : il porte le FakeEngine (en mémoire, dans son processus), consomme le bus, tient les projections et vérifie les commandes. L'API ne parle jamais à un moteur : elle écrit une commande, le worker la relève.
- **Bus** : Redis Streams, un stream `events`, un stream `commands`, groupes de consommateurs. Idempotence par `(instance_id, seq)` et par `id` d'événement.
- **Les relevés font foi** (§7) : un trou de séquence ou un doublon déclenche une relecture de `snapshot()` ; les projections sont recalculées d'après le moteur.
- **Valeur observée** : toute valeur issue d'un moteur sort de l'API sous la forme `{value, observed_at}` ; la réponse porte `server_time`. Le front calcule l'âge et applique les seuils (5 s flux, 30 s moteur). `unknown` est une valeur à part entière.
- **TOTP chiffré** : AES-256-GCM, clé maître en Docker secret. L'interface `SecretStore` complète reste à M2.
- **UUID v7** : une fonction de quelques lignes dans `centrade_core`, pas de dépendance.
- **Hors M1** : Risk service, kill switch (bouton présent, grisé), SecretStore, runner Docker, panneau « Garanties » (M4), graphiques (`lightweight-charts` n'entre pas à M1).

## Contrat d'API de M1 (préfixe `/api/v1`)

| Route | Rôle minimal | Notes |
| --- | --- | --- |
| `POST /auth/login` | — | mot de passe ; ouvre une pré-session, répond `totp_required` |
| `POST /auth/totp` | pré-session | code TOTP ou code de récupération ; pose le cookie `__Host-` |
| `POST /auth/logout`, `GET /auth/me` | session | |
| `GET /instances`, `GET /instances/{id}` | viewer | états voulu et observé, mode voulu et observé, `observed_at` |
| `POST /instances` | operator | instance simulée (moteur `fake`, mode paper) |
| `POST /instances/{id}/start`, `/stop`, `/pause-entries`, `/resume-entries`, `/flatten` | operator | `202` + `command_id`, `Idempotency-Key` obligatoire |
| `GET /commands`, `GET /commands/{id}` | viewer | statut et horodatage de chaque étape |
| `GET /events`, `GET /alerts`, `GET /audit` | viewer (`/audit` : admin) | pagination par curseur |
| `GET /stream` | viewer | SSE : battement, `instance`, `command`, `alert` |
| `GET /system/health` | — | base, bus, battement du worker |

Erreurs RFC 7807 (existant). Aucune route ne nomme un moteur précis.

## Lots

Dépendances : `A → B, C, E` ; `F → C` ; `C → D → G`.

| Lot | Contenu | Modèle | Vague |
| --- | --- | --- | --- |
| A | Socle : dépendances + ADR, disposition, settings, SQLAlchemy async, Alembic, tables de M1, audit (écriture, chaîne, trigger), masquage des logs, `conftest` testcontainers | sonnet | 1 |
| F | Contrat moteur, événements canoniques, FakeEngine et modes de panne, suite de conformité | sonnet | 1 |
| B | Auth : argon2id, TOTP, codes de récupération, sessions, RBAC, CSRF, verrouillage, `make bootstrap-admin` | opus, effort élevé | 2 |
| C | Bus, ingestion idempotente, projections, resynchronisation, worker (S9, propriétés) | sonnet | 2 |
| E | Front : coquille (barre persistante, navigation), client d'API, étape TOTP du login | sonnet | 2 |
| D | Instances, commandes et leur cycle, délais, SSE, santé, worker dans Compose (I1, I8, S10, I14) | sonnet | 3 |
| G | Cockpit en temps réel, règles de vérité de l'affichage, E2E + axe, captures de référence | sonnet | 4 |

## Risques

| Risque | Parade |
| --- | --- |
| Deux lots parallèles modifient `pyproject.toml` | Seul le lot A y touche ; les autres lots lui signalent un besoin |
| Le front affiche une valeur périmée comme actuelle | Composant unique `ObservedValue` ; test I1 côté API et test E2E |
| Test de délai lent ou instable (S10) | Horloge injectée dans le worker ; délais courts en test |
| `gitleaks`, `pre-commit`, `semgrep` absents du poste | Tournent en CI ; à installer par l'opérateur |

## Questions ouvertes

Aucune ne bloque. Hypothèses appliquées : liste ci-dessus, à reporter dans le README à la clôture.
