# ADR-0005 : Dépendances du front à M1

## Statut
Acceptée

## Date
2026-10-10

## Contexte
Le lot E de M1 (coquille, client d'API, connexion en deux étapes) a besoin de la ligne Frontend du §5 du SPEC qui avait été différée à M0 (ADR-0002) : TanStack Query pour l'état serveur (session, puis instances et commandes au Cockpit) et Zod pour valider chaque réponse de l'API. Versions exactes, lockfile pnpm figé.

## Décision

| Paquet | Version | Raison |
| --- | --- | --- |
| `@tanstack/react-query` | 5.104.1 | État serveur : session (`/auth/me`), puis flux et listes du Cockpit. Dans le §5. |
| `zod` | 4.6.5 | Schémas des réponses d'API et du problème RFC 7807 : une réponse hors contrat est refusée, jamais affichée. Dans le §5. |

Composants shadcn ajoutés par la CLI (aucune dépendance npm nouvelle, `radix-ui` est déjà installé) : `badge`, `tooltip`, `skeleton`, `empty`. Leurs imports ont été alignés sur l'alias `@/lib/utils` et `badge` a été restylé sur les jetons (variantes `default`, `live`, `unknown`).

Aucun routeur. Un seul écran est actif (Cockpit) et les neuf autres sont désactivés ; la garde de route est la requête `/auth/me`. Un routeur sera ajouté, avec son ADR, au premier jalon qui active un second écran.

## Audit de la chaîne d'approvisionnement
Outil : `supply-chain-risk-auditor` 2.0.4, sur les deux dépendances directes aux versions installées. `pnpm-lock.yaml` n'est pas lu par l'outil : le balayage transitif n'a pas eu lieu.

- Avis connus : aucun pour les deux paquets (2 sur 2 évalués).
- Paquet déprécié, dépôt archivé, activité de maintenance : rien à signaler (2 sur 2).
- Scripts d'installation : aucun signalé (2 sur 2).
- Provenance de publication : présente pour les deux.
- Politique de sécurité publiée : `zod` oui, `@tanstack/react-query` non (information, non bloquant).
- Concentration des éditeurs : non évaluable (2 sur 2) ; rapport Scorecard absent pour `@tanstack/react-query` sur plusieurs critères.
- Volume de téléchargement : 66 086 250 par semaine (`@tanstack/react-query`), 334 432 403 (`zod`).

## Alternatives écartées
- `react-router` : aucun écran à router tant que le Cockpit est seul actif.
- `fetch` + `useEffect` sans TanStack Query : réécrirait cache, annulation et rafraîchissement que le §5 impose déjà.
- Validation écrite à la main : refusée, la validation des réponses est un point de confiance (frontière réseau).
- `jsdom` et Testing Library : `ObservedValue` se teste par rendu serveur (`react-dom/server`) ; le comportement navigateur est couvert par Playwright.

## Conséquences
- Toute réponse d'API passe par `apiFetch(path, schemaZod)` ; les écrans ne manipulent que des données validées.
- Le balayage transitif reste à faire par un outil qui lit `pnpm-lock.yaml` (CI ou `pnpm audit`).
- Un routeur reste à décider avec l'activation du deuxième écran.
