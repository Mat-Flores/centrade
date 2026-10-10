# ADR-0002 : Dépendances du front à M0

## Statut
Acceptée

## Date
2026-10-10

## Contexte
Le §5 du SPEC fixe le front : React 18, TypeScript, Vite, Tailwind, shadcn/ui, TanStack Query, `lightweight-charts`, Zod, `pnpm`. M0 n'a qu'un écran (login) : TanStack Query, Zod et `lightweight-charts` ne sont pas installés, ils viendront avec les jalons qui les emploient. Les versions sont exactes (lockfile figé, `minimumReleaseAge` de pnpm respecté : `lucide-react` est en 1.54.0 car la 1.55.0 avait moins de 24 h).

## Décision
Dépendances hors de la ligne Frontend du §5 :

| Paquet | Raison |
| --- | --- |
| `@vitejs/plugin-react`, `@tailwindcss/vite` | Plugins officiels qui relient React et Tailwind v4 à Vite. |
| `radix-ui`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react` | Dépendances des composants shadcn/ui générés (style `radix-nova`) : primitives accessibles (Label, Separator, Slot), variantes, fusion de classes, icônes. |
| `@fontsource-variable/hanken-grotesk`, `@fontsource-variable/geist-mono` | Polices auto-hébergées, servies par l'application (CSP `font-src 'self'`, aucune ressource tierce). Hanken Grotesk pour l'interface, Geist Mono pour les identifiants et les nombres. |
| `vitest` | Lanceur de tests unitaires, natif Vite (même configuration que le build). |
| `@playwright/test`, `@axe-core/playwright` | Test de bout en bout et contrôle d'accessibilité exigés par le §9 (gates frontend). |
| `eslint`, `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `globals` | Lint exigé par le §9. |
| `@types/node` | Types de `node:path` pour `vite.config.ts` et les tests e2e. |

`typescript` reste en 6.0.3 : `typescript-eslint` 8.71 n'accepte pas encore TypeScript 7.

## Alternatives écartées
- Paquet `shadcn` et `tw-animate-css` (ajoutés par `shadcn init`) : retirés, aucun composant à overlay à M0.
- `jsdom` et Testing Library : la logique d'envoi se teste sans DOM ; le rendu est couvert par Playwright.
- Bibliothèque d'i18n : un module `src/i18n/fr.ts` suffit à M0.
- Polices Inter, Plex ou système : écartées par la direction artistique (SPEC §9).

## Conséquences
- Chaque dépendance ajoutée plus tard passe par `supply-chain-risk-auditor` et une ADR si elle sort du §5.
- Le test e2e exige les bibliothèques système de Chromium (`playwright install --with-deps chromium`, comme en CI).
