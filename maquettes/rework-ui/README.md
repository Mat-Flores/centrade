# Maquette interactive : refonte de l'interface Centrade

Maquette autonome des nouvelles interfaces, centrée sur l'instance. Elle ne touche à rien d'autre dans le dépôt : pas d'appel à l'API, aucune persistance, données inventées et marquées « simulé ». Ce n'est pas du code de production.

## Lancer

```sh
cd maquettes/rework-ui
pnpm install --ignore-workspace --ignore-scripts
pnpm dev
```

Puis ouvrir l'adresse affichée (par défaut http://localhost:5173/).

Autres commandes : `pnpm test` (tests des données et des calculs), `pnpm build` (vérification des types et construction).

## Ce que montre la maquette

- **Instances** : liste par mode (réel, test, backtest, jamais additionnés), création d'une instance.
- **Vue d'une instance, observation** : onglets « Tout » et par paire, indicateurs, composition (compte, stratégies partagées entre paires, automatisations), graphique de trading, journal des transactions.
- **Vue d'une instance, réglages** (à l'arrêt) : paires, stratégies, compte, automatisations, historique des versions.
- **Backtest** : import des données, simulation avec progression, lecture accélérée du résultat.
- **Passer en réel** : liste de contrôles, code TOTP, saisie du nom.
- **Bibliothèque** : clés, stratégies, automatisations.
- **Barre du haut** : arrêt d'urgence, thème clair ou sombre, personnalisation des couleurs, commandes de démonstration.

## Comportements propres à la maquette

- Le temps est accéléré : une bougie de 5 minutes toutes les 1,5 seconde. La série de prix dure 30 jours ; l'horloge s'arrête à la fin, après environ 43 minutes.
- Le bouton « Démo » de la barre du haut permet de faire échouer le prochain démarrage et de figer les données pour voir l'état « périmé ».
- Tout code TOTP à 6 chiffres est accepté.
- Recharger la page remet tout à zéro.

## Documents

| Fichier | Contenu |
| --- | --- |
| `PROMPT.md` | La demande d'origine. |
| `PRODUCT.md` | Brouillon du produit après cadrage. Ne remplace pas celui de la racine. |
| `ECARTS-SPEC.md` | Écarts avec `SPEC.md` et modifications qu'ils impliquent. |
| `VOCABULAIRE.md` | Mot courant à l'écran, terme technique en infobulle. |
| `docs/audit-dependances.md` | Audit des dépendances avant installation. |
| `captures/` | Captures de vérification (bureau et tablette, clair et sombre). |

## Hypothèses et limites

- **Pile** : React 18, TypeScript, Vite, Tailwind 4, Motion, GSAP, lightweight-charts. Polices Archivo et Martian Mono servies en local.
- **Montants** : nombres ordinaires, parce que les données sont inventées. Au portage dans `apps/web`, ils doivent devenir des chaînes décimales (`SPEC.md`).
- **Stratégies** : un croisement de moyennes trivial sert à produire des trades à afficher. Ce n'est pas une stratégie à utiliser, et la maquette ne dit rien d'un rendement.
- **Graphique** : la bibliothèque lightweight-charts (Apache-2.0) demande une mention d'attribution ; le logo TradingView reste affiché, et la mention reste à ajouter à une page de crédits au portage.
- **Lecture d'un backtest** : c'est une mise en scène du résultat calculé, pas une seconde exécution.
