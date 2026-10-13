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
- **Bibliothèque** : clés, stratégies (par provider, avec la fenêtre de création d'une stratégie Freqtrade), automatisations.
- **Barre du haut** : navigation, état de la connexion aux bots, arrêt d'urgence, menu du compte (thème, couleurs, disposition, paramètres, démo, déconnexion).
- **Connexion** : écran d'identification, atteint par « Se déconnecter ».

## Comportements propres à la maquette

- Le temps est accéléré : une bougie de 5 minutes toutes les 1,5 seconde. La série de prix dure 30 jours ; l'horloge s'arrête à la fin, après environ 43 minutes.
- Le bouton « Démo » de la barre du haut permet de faire échouer le prochain démarrage et de figer les données pour voir l'état « périmé ».
- Tout code TOTP à 6 chiffres est accepté.
- Recharger la page remet tout à zéro, y compris la disposition du tableau de bord.
- La maquette s'ouvre connectée ; l'écran de connexion accepte n'importe quel identifiant et tout code à 6 chiffres.

## Manipuler le tableau de bord d'une instance

- **Replier une zone** : clic n'importe où sur son en-tête (Solde, Indicateurs, Composition, Graphique, Résultats par paire, Journal).
- **Déplacer une zone** : glisser son en-tête sur une autre zone, elles échangent leurs places. Solde et Indicateurs s'échangent entre eux ; les autres zones, entre elles. Pas de glisser-déposer au tactile.
- **Défilement** : l'écran d'une instance défile. Au centre, chaque zone a sa hauteur, réglable par son bord bas jusqu'à l'écran entier. Les colonnes de gauche et de droite ne se règlent pas en hauteur : elles couvrent la partie visible de la colonne du centre (même haut, même bas) et grandissent à mesure que le haut de la page sort de la vue. Leur hauteur rattrape le défilement par une transition courte, pour rester fluide.
- **Zone repliée** : repliée en hauteur, une zone garde sa largeur, toujours réglable ; dans une colonne latérale, elle se replie en largeur (rail).
- **Redimensionner** : bords des colonnes de la grille, et bords des titres de colonnes dans les tableaux (double clic pour revenir au défaut).
- **Réinitialiser la disposition** : menu du compte, ou page Paramètres.
- **Journal** : clic sur un trade pour le déplier, double clic pour le voir sur le graphique, clic droit (ou « … ») pour le menu des actions.
- **% ou devise** : un clic sur une variation en % l'affiche dans la devise du compte, pour toute l'interface ; un second clic revient au %.
- **Aperçu de survol** : tout texte coupé par « … » se lit en entier au survol ; une valeur suivie de l'icône de copie se copie d'un clic.

## Providers

Une instance appartient à un provider (le moteur de trading : Freqtrade), choisi à la création et modifiable seulement tant qu'elle n'a ni paire ni démarrage. Une stratégie appartient elle aussi à un provider et ne s'affecte qu'à une instance du même provider. Chaque provider a sa propre fenêtre de création de stratégie ; seule celle de Freqtrade existe (nom, description, code Python, politique de sortie, paramètres). NautilusTrader figure dans la liste comme provider « pas encore pris en charge », pour montrer le cas.

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
- **Contrôles du code d'une stratégie** : rejoués dans le navigateur par expressions régulières, pour montrer l'interface. Le vrai contrôle est `packages/adapters/freqtrade/centrade_freqtrade/checks.py`, côté serveur.
- **Barres de défilement et aperçus de survol** : dessinés par la maquette (`src/ui/scrollbars.ts`, `src/ui/tips.ts`), avec l'API Popover des navigateurs récents.
- **Stratégies** : un croisement de moyennes trivial sert à produire des trades à afficher. Ce n'est pas une stratégie à utiliser, et la maquette ne dit rien d'un rendement.
- **Graphique** : la bibliothèque lightweight-charts (Apache-2.0) demande une mention d'attribution ; le logo TradingView reste affiché, et la mention reste à ajouter à une page de crédits au portage.
- **Lecture d'un backtest** : c'est une mise en scène du résultat calculé, pas une seconde exécution.
