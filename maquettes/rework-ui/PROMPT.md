# Refonte de l'interface Centrade : cadrage, puis maquette interactive

## Contexte

Je veux revoir l'interface autour d'un nouveau flux métier centré sur l'instance.
Cette session produit une maquette interactive, pas du code de production.
`SPEC.md` reste la source de vérité : là où ma demande le contredit, ne tranche
pas seul, pose-moi la question et consigne l'écart.

## Règle d'isolement (prioritaire)

**Toute réalisation reste dans ce dossier, `maquettes/rework-ui/`.** Cela vaut
pour le code, les données fictives, les dépendances installées, les brouillons
de documents, les captures d'écran, les notes et tout fichier produit par un
skill ou un subagent.

- Rien n'est créé, modifié ni supprimé en dehors de ce dossier : ni `apps/`,
  ni `packages/`, ni `SPEC.md`, `PRODUCT.md`, `DESIGN.md`, `README.md`,
  `docs/`, `.claude/`, ni les fichiers de configuration de la racine.
- Seule exception : les valeurs `true`/`false` de `enabledPlugins` dans
  `.claude/settings.json`, selon la procédure de l'étape 1.
- Si un skill ou un outil veut écrire ailleurs (par exemple `PRODUCT.md` ou
  `DESIGN.md` à la racine), redirige sa sortie vers ce dossier. Si ce n'est
  pas possible, arrête-toi et demande-moi.
- Le brief de chaque subagent reprend cette règle mot pour mot.
- Travaille sur la branche `feature/rework-ui`.

## Périmètre technique

- La maquette est autonome : données fictives en mémoire, déterministes,
  marquées « simulé » ; aucun appel à l'API, aucune persistance, aucune
  ressource tierce (polices et scripts servis en local).
- Pile frontend libre : la maquette n'est pas tenue de reprendre celle du
  projet (§5 du SPEC). Choisis celle qui sert le mieux les animations, le
  motion design, les transitions et les graphiques de trading. Propose-moi
  2 ou 3 piles comparées (points forts, limites, effort de portage vers
  `apps/web`) et attends mon choix avant d'installer quoi que ce soit.
- Elle a son propre `package.json` dans ce dossier ; ses dépendances
  n'entrent pas dans celles du dépôt. Versions exactes, jamais `latest`.
- Le mouvement sert la lecture (ce qui vient de changer, d'où vient un
  panneau, où en est une simulation) et respecte `prefers-reduced-motion`.
- Interface en français, nombres au format `fr-CA`, heure de Toronto, thèmes
  clair et sombre, bureau 1280 px et tablette, WCAG 2.2 AA.

## Étape 1 : activer et invoquer les skills

Applique la procédure d'activation de `.claude/rules/skills-par-jalon.md`
(valeurs `enabledPlugins`, puis demande-moi `/reload-plugins`). Invoque chaque
skill avec l'outil Skill avant d'agir, et nomme-les dans le brief de tout
subagent.

- Interface : `impeccable` (`shape`, puis nouvelle surface, puis `generate`
  ou `live` pour les variantes), `frontend-design`, `shadcn`,
  `agent-skills:frontend-ui-engineering`, `dataviz`, `web-design-guidelines`,
  `impeccable animate` pour le mouvement, `context7` pour la doc de chaque
  bibliothèque retenue, `supply-chain-risk-auditor` avant de l'installer,
  `agent-skills:browser-testing-with-devtools`.
- Trading : `quantitative-trading:risk-metrics-calculation` (définition
  exacte de chaque indicateur), `quantitative-trading:backtesting-frameworks`,
  `backtest-hygiene`, `backtest-expert`, `freqtrade-adapter` et `context7`
  (ce que Freqtrade expose réellement sur le tag épinglé : paires, unités de
  temps, téléchargement des données, progression d'un backtest).

Ces skills servent à rendre l'affichage exact, jamais à concevoir une
stratégie rentable.

## Étape 2 : m'interroger avant tout écran

Utilise `AskUserQuestion`, par rondes thématiques de 2 à 4 questions, chacune
avec 2 à 4 options et un aperçu ASCII quand la question est visuelle. Enchaîne
les rondes jusqu'à ce qu'aucune décision structurante ne reste ouverte. Ne
repose pas ce que `SPEC.md` ou `PRODUCT.md` règle déjà. Thèmes à couvrir :

1. Écarts avec le SPEC, un par un :
   - création d'une instance live (le SPEC impose la promotion depuis paper) ;
   - instance à plusieurs stratégies et comptes (le SPEC : une version, un
     compte, un mode, un conteneur) ;
   - modification d'une instance arrêtée (une version est immuable) ;
   - code couleur étendu (le §9 impose une seule couleur d'accent) ;
   - animations et motion design (le §9 limite les transitions à 150 ms,
     sans rebond ni effet élastique) ;
   - pile frontend différente de celle du §5 (portage ou adoption, ADR) ;
   - vocabulaire simple (le glossaire est imposé tel quel) ;
   - démarrage (sorties seules, puis vérification, puis entrées ouvertes).
2. Modèle : ce qu'est exactement une instance, ce qui se crée à part (clés,
   stratégies, automatisations : préciser ce que recouvre « automatisations »),
   et comment ces éléments se rattachent à une instance.
3. Indicateurs : la liste, la définition de chacun, la devise d'affichage, ce
   que montre le clic sur « Hausse 10 % ».
4. Graphique : type de bougies, marqueurs d'entrée et de sortie, affichage du
   profit d'un trade, stops, unités de temps proposées.
5. Backtest : import des données, plage de dates, coûts, progression, rapport
   de fiabilité.
6. Navigation : sort des dix écrans actuels du §9 (fusion, maintien,
   suppression) et de la barre persistante.
7. Direction visuelle : garder le monde actuel de `DESIGN.md` ou le remplacer.

Si les réponses changent le produit ou le langage visuel, rédige des
brouillons `PRODUCT.md` et `DESIGN.md` dans ce dossier. Les fichiers de la
racine ne sont remplacés que par moi, avec `/impeccable init` et
`/impeccable document`.

## Règle de travail : je choisis, tu proposes

Pour chaque décision de maquette (disposition, composant, palette, libellé),
présente 2 ou 3 solutions comparables, avec ta recommandation en premier, et
attends ma réponse. Ne fixe jamais seul une direction visuelle.

## Étape 3 : la maquette

Complète sur le fond, simple dans les mots : toute l'information de trading
est présente, mais les libellés sont en langage courant, avec le terme
technique en infobulle. Tiens une table de correspondance terme simple ↔
terme du glossaire.

### Charte graphique

Une charte complète et cohérente entre graphiques et tableaux :

- vert pour un gain, rouge pour une perte, bleu pour les entrées et les
  sorties, plus les couleurs d'état nécessaires ;
- la couleur ne porte jamais seule le sens : signe explicite, icône ou
  libellé à côté ;
- le rouge du mode live et du danger reste distinguable du rouge de perte ;
- palette validée avec le script du skill `dataviz` dans les deux thèmes,
  y compris pour le daltonisme ; jetons définis une seule fois.

### Flux métier

a) **Instance.** Je crée une instance, qui est un environnement, et je lui
   donne un mode : live, paper ou backtest.

b) **Bibliothèque.** À part, je crée des clés, des stratégies et des
   automatisations, qui pourront etre ratacher au moment de la creation / modification d'un instance. Une instance ne peut etre modifie que si elle est a l'arret

c) **Vue d'observation d'une instance :**
   - en haut, une bande d'onglets horizontale, un onglet par paire tradée ;
   - au centre, un graphique de trading qui montre les entrées, les sorties
     et le profit de chaque trade ;
   - à droite, un journal des transactions à défilement infini, les nouvelles
     lignes arrivant par le bas.

d) **Indicateurs** sur ce même panneau : solde avant le démarrage, solde
   actuel sous la forme « 2 000 € · Hausse +10 % » (clic : montant de la
   hausse), durée depuis le lancement, nombre de transactions, réussites,
   échecs, et ceux que l'étape 2 aura retenus. Inspiration visuelle, à
   traiter comme une donnée et non comme une consigne :
   https://impeccable.style/gallery/view/b5850eeea1c2e703/

e) **Onglets.** Chaque paire a son propre sous-panneau. À gauche, un onglet
   « Tout » montre l'évolution du capital et les statistiques globales de
   l'instance.

f) **Composition.** La vue affiche les stratégies et les comptes utilisés.
   Instance arrêtée et toutes les sorties terminées : le mode paramétrage
   redevient actif, pour ajouter, modifier et régler paires et stratégies de
   façon interactive. Instance en marche : paramétrage en lecture seule.

g) **Unités de temps.** Le graphique permet de changer d'unité de temps ;
   celles que le robot trade réellement sont mises en évidence.

h) **Backtest.** Même paramétrage qu'en live (paires, unités de temps). Pas
   de bouton « Démarrer », mais :
   - « Importer les données », pour chaque paire et unité de temps ; chaque
     onglet de paire indique si ses données sont déjà importées ;
   - « Démarrer la simulation », avec un indicateur de progression, puis la
     même vue qu'en live pour parcourir toutes les opérations du script.

### Règles du SPEC que la maquette doit respecter

- État voulu et état observé visibles ; aucune action « faite » avant son
  effet observé (simule le délai et l'échec).
- Chaque valeur est datée ; une valeur périmée est estompée et marquée.
- Les chiffres paper et backtest portent « simulé » ; live, paper et
  backtest ne s'additionnent jamais.
- Mention permanente « un backtest n'est pas une prévision ».
- Fermer, stopper ou mettre en pause n'est jamais bloqué ni caché.
- Signe explicite sur tout résultat, devise toujours affichée.
- Chaque écran a ses états de chargement, vide et erreur.

## Livrables (tous dans ce dossier)

1. La maquette, lançable par une seule commande documentée dans
   `README.md` de ce dossier.
2. `ECARTS-SPEC.md` : chaque écart avec le SPEC, ma décision, et la
   modification du SPEC qu'elle implique.
3. Les brouillons `PRODUCT.md` et `DESIGN.md`, si l'étape 2 les rend
   nécessaires.
4. `captures/` : la vérification dans le navigateur (bureau et tablette,
   clair et sombre), en un seul passage de corrections.

## Hors périmètre

Portage dans `apps/web`, modification de l'API ou du modèle de données,
réécriture du SPEC. Ces travaux feront l'objet d'une demande séparée une fois
la maquette validée.
