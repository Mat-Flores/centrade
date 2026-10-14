# ADR-0011 : `web-stack`, pile web de V2

## Statut
Acceptée (opérateur, 2026-10-14)

## Date
2026-10-14

## Contexte
V2 fusionne la nouvelle interface (`maquettes/rework-ui/`) avec la couche de données de la V1 (`apps/web`). La maquette apporte composants, CSS et graphiques ; la V1 apporte le client d'API validé par Zod, TanStack Query, le flux SSE et l'arithmétique décimale. La simulation de la maquette (`data/store.ts`, `sim.ts`, `seed.ts`) est supprimée : V2 n'affiche que ce que l'API renvoie.

## Décision

| Paquet | Version | Rôle |
| --- | --- | --- |
| `react`, `react-dom` | 18.3.1 | interface |
| `@tanstack/react-query` | 5.104.1 | état serveur (session, listes, flux) |
| `zod` | 4.6.5 | chaque réponse d'API est validée, une réponse hors contrat est refusée |
| `lightweight-charts` | 5.2.1 | graphiques de prix et d'equity |
| `motion` | 13.4.4 | transitions et animations de composants |
| `gsap`, `@gsap/react` | 3.15.0, 2.1.2 | séquence de démarrage et un effet du graphique, seulement |
| `@fontsource-variable/archivo`, `@fontsource-variable/martian-mono` | 5.3.0 | polices servies localement (CSP `font-src 'self'`) |
| `tailwindcss`, `@tailwindcss/vite` | 4.3.3 | CSS de la maquette |

- Routeur maison sur l'API History, avec chemins réels (pas de hash) ; aucune dépendance de routage.
- Retirés par rapport à la V1 : `shadcn/ui`, `radix-ui`, `class-variance-authority`, `tailwind-merge`, ainsi que `clsx`, `lucide-react` et les polices Geist et Hanken Grotesk, que la maquette n'utilise pas.
- Tests : `vitest` (unitaires) et Playwright (projets `mock` et `live`), comme en V1.
- Versions exactes, reprises des deux `package.json` ; aucune nouvelle dépendance par rapport à ces deux sources.
- Code, identifiants et commentaires en anglais ; les textes affichés sont en français et vivent dans `src/i18n/fr.ts`.

## Audit de la dépendance
Aucun paquet nouveau : tous figurent déjà dans la V1 ou la maquette, déjà auditées. `motion` et `gsap` sont gardés ensemble sur décision de l'opérateur ; leur usage reste séparé (GSAP limité aux deux cas ci-dessus) pour ne pas doubler les moteurs d'animation.

## Conséquences
- La CSP de production (`style-src 'self'`) doit être vérifiée par l'e2e avec Motion et GSAP, qui écrivent des styles en ligne via le CSSOM.
- Les montants restent des chaînes décimales de bout en bout ; les fonctions de la maquette qui prenaient des `number` pour l'argent ne sont pas reprises.
