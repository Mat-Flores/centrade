---
name: Centrade, maquette rework-ui
description: Brouillon du système visuel de la maquette. Terminal de trading dense qui montre ce qu'un bot a réellement fait.
colors:
  ground: "#0e1116"
  panel: "#12161d"
  raised: "#171c25"
  line: "#232a35"
  line-2: "#2e3643"
  bone: "#e8e6df"
  dim: "#8f97a4"
  faint: "#7d8694"
  bid: "#2fbf71"
  ask: "#e5484d"
  amber: "#f2b233"
  amber-hover: "#ffc550"
  amber-ink: "#1a1305"
  blue: "#4c8dff"
  violet: "#a78bfa"
  ground-light: "#f4f3ef"
  panel-light: "#fbfaf7"
  raised-light: "#eceae4"
  line-light: "#d9d6cd"
  line-2-light: "#c4c0b5"
  bone-light: "#14181f"
  dim-light: "#555d6b"
  faint-light: "#6b7381"
  bid-light: "#177a45"
  ask-light: "#c4262c"
  amber-light: "#a84a06"
  accent-light: "#1d2530"
  accent-hover-light: "#38434f"
  accent-ink-light: "#fbfaf7"
  blue-light: "#1f5fd6"
  violet-light: "#6d3fd1"
  cvd-gain: "#2b7fe0"
  cvd-loss: "#d9730d"
  cvd-action: "#16a085"
  cvd-mode-reel: "#d946b5"
typography:
  title:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "21px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.02em"
    fontVariation: "'wdth' 72"
  subtitle:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    lineHeight: 1.2
    fontVariation: "'wdth' 80"
  body:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
    fontVariation: "'wdth' 100"
  control:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.01em"
    fontVariation: "'wdth' 88"
  panel-head:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
  row-text:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 400
  data:
    fontFamily: "Martian Mono Variable, ui-monospace, Menlo, monospace"
    fontSize: "12px"
    fontWeight: 400
    fontFeature: "'tnum', 'zero'"
  label:
    fontFamily: "Martian Mono Variable, ui-monospace, Menlo, monospace"
    fontSize: "11px"
    fontWeight: 400
    letterSpacing: "0.06em"
rounded:
  none: "0"
  control: "2px"
spacing:
  row: "22px"
  cols: "26px"
  btn-sm: "32px"
  tab: "36px"
  btn: "40px"
  head: "40px"
  touch: "44px"
  bar: "52px"
  tight: "6px"
  cell: "10px"
  pad: "12px"
  group: "14px"
  page: "16px"
components:
  button:
    backgroundColor: "transparent"
    textColor: "{colors.bone}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0 18px"
    height: "{spacing.btn}"
  button-go:
    backgroundColor: "{colors.amber}"
    textColor: "{colors.amber-ink}"
    rounded: "{rounded.control}"
    padding: "0 18px"
    height: "{spacing.btn}"
  button-go-hover:
    backgroundColor: "{colors.amber-hover}"
    textColor: "{colors.amber-ink}"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{colors.ask}"
    rounded: "{rounded.control}"
    height: "{spacing.btn}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.dim}"
    rounded: "{rounded.control}"
  button-sm:
    padding: "0 12px"
    height: "{spacing.btn-sm}"
  button-xs:
    padding: "0 8px"
    height: "24px"
  segmented:
    backgroundColor: "transparent"
    textColor: "{colors.dim}"
    rounded: "{rounded.control}"
    padding: "0 10px"
    height: "{spacing.cols}"
  segmented-pressed:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.bone}"
  tag:
    backgroundColor: "transparent"
    textColor: "{colors.dim}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "1px 5px"
  tag-sim:
    backgroundColor: "transparent"
    textColor: "{colors.amber}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "3px 4px 2px"
  mode-test:
    backgroundColor: "transparent"
    textColor: "{colors.amber}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "4px 6px 3px"
  mode-backtest:
    backgroundColor: "transparent"
    textColor: "{colors.violet}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "4px 6px 3px"
  mode-reel:
    backgroundColor: "{colors.ask}"
    textColor: "{colors.ground}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "4px 6px 3px"
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.bone}"
    rounded: "{rounded.none}"
  panel-head:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.bone}"
    typography: "{typography.panel-head}"
    padding: "0 12px"
    height: "{spacing.head}"
  cols-header:
    textColor: "{colors.faint}"
    typography: "{typography.label}"
    padding: "0 10px"
    height: "{spacing.cols}"
  data-row:
    textColor: "{colors.bone}"
    typography: "{typography.data}"
    padding: "0 10px"
    height: "{spacing.row}"
  data-row-selected:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.bone}"
  tab:
    backgroundColor: "transparent"
    textColor: "{colors.dim}"
    padding: "0 14px"
    height: "{spacing.tab}"
  tab-selected:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.bone}"
  input:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.bone}"
    rounded: "{rounded.control}"
    padding: "0 10px"
    height: "{spacing.btn-sm}"
  dialog:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.bone}"
    rounded: "{rounded.control}"
    width: "min(560px, calc(100vw - 32px))"
  tooltip:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.bone}"
    rounded: "{rounded.none}"
    padding: "8px 10px"
  top-bar:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.bone}"
    padding: "0 16px"
    height: "{spacing.bar}"
---

<!-- BROUILLON : système visuel de la maquette maquettes/rework-ui/. Ne remplace pas le DESIGN.md de la racine du dépôt. -->

# Design System: Centrade, maquette rework-ui

> **Brouillon.** Ce document décrit la maquette `maquettes/rework-ui/` telle qu'elle a été construite le 12 octobre 2026. Il ne remplace pas le `DESIGN.md` de la racine du dépôt, qui reste celui de l'application en production. Seul l'opérateur peut décider de le remplacer. Chaque valeur ci-dessous vient du code livré (`src/theme/tokens.css`, `src/ui/ui.css`, `src/chart/chart.css`, `src/app/app.css`, `src/screens/instance/instance.css`, `src/theme/colors.ts`) et des captures de `captures/`. Les écarts entre fichiers ne sont pas des règles : ils sont listés à part par l'auteur du relevé.

## Overview

**Creative North Star: "Le terminal de constat"** (nom proposé, à confirmer par l'opérateur)

L'écran d'une instance est un terminal de trading dense. Il montre ce qu'un bot a réellement fait : ce qu'il a gagné ou perdu, pourquoi, et ce qu'il fait maintenant. Il refuse le tableau de bord aéré fait de cartes. L'information tient dans des panneaux à plat, collés les uns aux autres et séparés par des filets d'un pixel. Les lignes de données font 22 px de haut et les chiffres sont à chasse fixe.

Le monde visuel est repris de la page de référence fixée par l'opérateur (feuille de style copiée dans `.impeccable/reference.css`) : fond presque noir, texte couleur os, vert et rouge de carnet d'ordres, ambre pour l'action principale et les avertissements, titres condensés en capitales (Archivo), chiffres tabulaires (Martian Mono). La maquette y ajoute trois choses absentes de la référence : un bleu pour les achats, les ventes et ce qui est en cours, un violet pour le mode backtest, et un thème clair.

Ce qui est vrai passe avant ce qui rassure. Un état est daté, un chiffre de test porte la mention « simulé », une valeur périmée est estompée. Le mouvement ne sert qu'à montrer un changement réel.

**Key Characteristics:**
- Densité de terminal : barre de 52 px, en-têtes de panneau de 40 px, titres de colonnes de 26 px, lignes de 22 px.
- Tout est à plat : filets de 1 px, aucune ombre portée, coins de 0 ou 2 px.
- Deux polices seulement : Archivo pour les mots, Martian Mono pour les chiffres et les libellés.
- Chaque couleur a un seul sens, le même sur le graphique, dans les tableaux et dans les indicateurs.
- La couleur n'est jamais seule : un signe, une flèche ou un libellé l'accompagne.
- Sombre par défaut, clair disponible, couleurs de sens personnalisables.

## Colors

Une palette de carnet d'ordres sur fond presque noir : des neutres froids, un texte chaud couleur os, et cinq couleurs de sens bien séparées. Les valeurs sont dans l'en-tête du fichier ; le texte ci-dessous donne leur rôle.

Les composants ne lisent jamais une couleur brute. Ils lisent des rôles, les variables `--c-*`, et ce sont ces rôles que l'opérateur personnalise.

### Primary
- **Ambre** (`amber`, rôles `--c-accent`, `--c-warn`, `--c-mode-test`) : l'action principale d'un écran (bouton plein), le trait de 2 px qui marque l'élément sélectionné, le contour de focus, les avertissements, et tout ce qui est simulé (mention « simulé », étiquette « mode test », toutes deux en pointillés). Au survol, le bouton plein passe à `amber-hover`. Le texte posé sur l'ambre est `amber-ink`.

### Secondary
- **Vert de gain** (`bid`, rôles `--c-gain`, `--c-candle-up`) : un gain encaissé, une bougie en hausse, une étape de démarrage constatée.
- **Rouge de perte et de danger** (`ask`, rôles `--c-loss`, `--c-candle-down`, `--c-mode-reel`) : une perte encaissée, une bougie en baisse, une erreur, une commande qui réduit le risque (« Tout vendre », « Arrêter », « Arrêt d'urgence »), et le mode réel.

### Tertiary
- **Bleu d'action** (`blue`, rôle `--c-action`) : les achats, les ventes, et tout ce qui est en cours (variation non encaissée, étape en cours, portion de courbe entre un achat et une vente, ligne sélectionnée du journal).
- **Violet de backtest** (`violet`, rôle `--c-mode-backtest`) : le mode backtest, et rien d'autre.

### Neutral
- **Fond** (`ground`, rôle `--c-bg`) : le fond de page, le fond des champs et de l'infobulle du graphique.
- **Panneau** (`panel`, rôle `--c-surface`) : le fond de tous les panneaux, du graphique et des boîtes de dialogue.
- **Surface relevée** (`raised`, rôle `--c-raised`) : la ligne survolée ou sélectionnée, les panneaux flottants, le pied de tableau.
- **Filet** (`line`, rôle `--c-line`) : les bordures de panneau et les séparations. Entre deux lignes de données, le filet est adouci à 55 % d'opacité.
- **Filet fort** (`line-2`, rôle `--c-line-2`) : le contour des boutons, des champs et des panneaux flottants.
- **Os** (`bone`, rôle `--c-ink`) : le texte principal.
- **Gris moyen** (`dim`, rôle `--c-mute`) : le texte secondaire, les onglets au repos.
- **Gris discret** (`faint`, rôle `--c-faint`) : les libellés de colonnes et les mentions de troisième rang.

### Teintes de fond dérivées

Trois dispositifs repris de la référence utilisent une couleur de sens fortement diluée. Ils sont calculés à partir du rôle, donc ils suivent le thème et la personnalisation.

- **Barre de chaleur** : un aplat à 16 % du vert, du rouge ou du bleu, placé derrière un chiffre et dont la largeur est proportionnelle à la valeur.
- **Bande hachurée** : des rayures à 135 degrés, ambre à 14 % puis à 5 %, par pas de 6 px. Elle marque un danger en cours (bandeau d'arrêt d'urgence) ou un achat refusé par une protection dans le journal.
- **Éclair de ligne** : à l'arrivée d'une ligne dans le journal, un fond à 45 % de la couleur de sens qui s'efface.

### Thème clair

Le thème clair s'active avec `data-theme="light"` sur `<html>`. Il garde les mêmes teintes et inverse la luminosité : papier chaud pour les fonds (`ground-light`, `panel-light`, `raised-light`), encre presque noire pour le texte (`bone-light`), et des couleurs de sens assombries pour rester lisibles sur clair (`bid-light`, `ask-light`, `blue-light`, `violet-light`, `amber-light`). Exception, depuis le 13 octobre 2026 : en clair, l'accent (`--accent`, boutons principaux et sélection) est l'encre `accent-light`, et `amber-light` ne sert plus qu'aux avertissements et au mode test ; en sombre, l'accent reste l'ambre. Pour le reste, seules les valeurs brutes changent ; les rôles `--c-*`, les dimensions et les composants sont identiques. Le graphique relit sa palette à chaque changement de thème. Le thème sombre est le thème par défaut et le thème n'est pas mémorisé dans la maquette.

Contrastes mesurés sur le code livré (texte sur `panel`, puis sur `raised`) :

| Couleur | Sombre | Clair |
| --- | --- | --- |
| Texte principal | 14,5:1, 13,7:1 | 17,1:1, 14,8:1 |
| Texte secondaire | 6,2:1, 5,8:1 | 6,4:1, 5,5:1 |
| Libellés discrets | 4,9:1, 4,6:1 | 4,6:1, 4,0:1 |
| Vert | 7,6:1, 7,2:1 | 5,2:1, 4,5:1 |
| Rouge | 4,6:1, 4,4:1 | 5,5:1, 4,8:1 |
| Bleu | 5,7:1, 5,3:1 | 5,5:1, 4,8:1 |
| Ambre | 9,7:1, 9,1:1 | 5,6:1, 4,8:1 |
| Violet | 6,7:1, 6,3:1 | 6,1:1, 5,3:1 |

Deux cases passent sous 4,5:1 : le rouge sombre sur une ligne relevée (4,4:1) et les libellés discrets clairs sur une ligne relevée (4,0:1). Ce sont des défauts relevés, pas des valeurs à reproduire.

### Rôles personnalisables et préréglages

Huit rôles sont réglables par l'opérateur dans la boîte « Couleurs » : gain, perte, achats/ventes/en cours, bougie en hausse, bougie en baisse, mode test, mode réel, backtest. Le réglage pose la variable `--c-*` correspondante sur `<html>` et prévient le graphique. Quatre préréglages existent :

- **Référence** : les couleurs ci-dessus.
- **Adapté au daltonisme** : gain en bleu (`cvd-gain`), perte en orange (`cvd-loss`), achats et en cours en vert-bleu (`cvd-action`), mode réel en magenta (`cvd-mode-reel`) pour rester distinct de l'orange des pertes.
- **Inversé (marchés asiatiques)** : le rouge pour un gain, le vert pour une perte, bougies comprises.
- **Bougies neutres** : bougies en os et en gris, le reste inchangé.

À chaque réglage, un contrôle signale un rôle dont le contraste sur le panneau passe sous 3:1, et six paires de rôles devenues trop proches (distance OKLab × 100 sous 15) : gain et perte, gain et en cours, perte et en cours, les deux bougies, mode réel et mode test, mode réel et perte.

### Accessibilité des couleurs

En vision daltonienne simulée (deutéranopie), le vert et le rouge de la référence ne sont séparés que de 6 à 8 points environ (7,8 en sombre, 6,3 en clair), très en dessous du seuil de 15 utilisé par la maquette. La couleur ne suffit donc pas à distinguer un gain d'une perte. Le préréglage adapté au daltonisme remonte la paire la plus faible à 12,2. En tritanopie simulée, le vert et le bleu de la référence se rapprochent aussi (7,2 en sombre, 5,6 en clair) : les mots « encaissé » et « en cours » font la différence.

### Named Rules

**La règle du sens unique.** Vert veut dire gain. Rouge veut dire perte ou danger. Bleu veut dire achat, vente ou en cours. Ambre veut dire action principale, avertissement ou simulé. Violet veut dire backtest. Une couleur de sens ne sert jamais de décor.

**La règle de la couleur accompagnée.** Aucun sens n'est porté par la couleur seule. Un résultat a toujours son signe et sa flèche, une variation a toujours son mot (« encaissé », « en cours »), un état a toujours son libellé.

**La règle du réel plein.** L'étiquette du mode réel est la seule étiquette à fond plein. Le mode test est en pointillés, le backtest en trait continu. Le réel ne se confond avec rien, même sans la couleur.

**La règle des rôles.** Un composant lit `--c-gain`, `--c-loss`, `--c-action` et les autres rôles, jamais `--bid`, `--ask` ou un code couleur. Sinon la personnalisation et le thème clair cessent de fonctionner.

## Typography

**Display Font:** Archivo Variable, axe de largeur resserré (repli : system-ui, sans-serif)
**Body Font:** Archivo Variable, largeur normale (repli : system-ui, sans-serif)
**Label/Mono Font:** Martian Mono Variable (repli : ui-monospace, Menlo, monospace)

**Character:** Une seule famille sans empattement, dont on resserre la largeur pour les titres, face à une police à chasse fixe pour tout ce qui se compte. Les deux polices sont servies en local, sans ressource tierce.

### Hierarchy
- **Titre** (800, 21 px, interligne 1, largeur 72, interlettrage 0,02em, capitales) : le nom de l'instance, le titre d'une page, le nom du produit dans la barre du haut.
- **Sous-titre** (700, 15 px, interligne 1,2, largeur 80) : le nom d'une stratégie ou d'une section dans un panneau.
- **Corps** (400, 15 px, interligne 1,5) : la taille de base de la page. Le texte courant des panneaux et des dialogues est en 13 px.
- **Commande** (600, 14 px, largeur 88, interlettrage 0,01em) : le texte des boutons. 13 px pour les petits boutons et les onglets, 12 px pour les choix segmentés.
- **En-tête de panneau** (600, 13 px) : le titre d'un panneau, dans sa bande de 40 px.
- **Texte de ligne** (400, 12,5 px, Archivo) : les mots dans une ligne de données (nom, description d'un événement), et les messages d'avertissement.
- **Donnée** (Martian Mono, 400, 12 px, chiffres tabulaires et zéro barré) : tous les chiffres des lignes de 22 px. La même police passe à 15 px pour une valeur d'indicateur en vue tablette et à 21 px pour le solde.
- **Libellé** (Martian Mono, 400, 11 px, interlettrage 0,06em, capitales) : les titres de colonnes, le nom d'un indicateur, l'intitulé d'un groupe dans un panneau. Les étiquettes utilisent la même taille avec un interlettrage de 0,04 à 0,08em.

Tailles réellement utilisées : 11, 12, 12,5, 13, 14, 15 et 21 px. Le texte courant de la référence est court ; aucune longueur de ligne n'est fixée, sauf 72 caractères pour les deux paragraphes explicatifs des écrans secondaires.

### Named Rules

**La règle du chiffre à chasse fixe.** Tout nombre est en Martian Mono, avec chiffres tabulaires et zéro barré. Un chiffre qui change ne déplace jamais ses voisins.

**La règle du libellé de donnée.** Le petit texte en capitales à chasse fixe nomme une colonne, un indicateur ou un groupe de données. Il ne se pose pas au-dessus d'un titre pour faire joli.

**La règle de la largeur.** La hiérarchie se fait par la largeur et la graisse d'Archivo (72, 80, 88, 100), pas par une troisième police ni par de grandes tailles.

## Layout

L'écran d'une instance occupe toute la hauteur de la fenêtre, sans défilement de page sur bureau. De haut en bas :

1. la barre du haut (52 px, collante) : nom du produit, navigation, bandeau des instances, état des bots, outils, arrêt d'urgence ;
2. la barre de l'instance (48 px au minimum) : nom, étiquette de mode, état constaté et daté, bascule Observation / Réglages, commandes ;
3. les onglets (36 px) : « Tout », puis un onglet par paire avec sa variation ;
4. la bande d'indicateurs (67 px) : le solde et ses deux variations à gauche, puis les indicateurs rangés en colonnes de trois lignes de 22 px, puis le compteur d'indicateurs actifs à droite ;
5. la grille d'observation, qui prend le reste : composition à gauche (248 px), graphique au centre (largeur restante), journal des transactions à droite (340 px).

Les panneaux se touchent. Ils sont séparés par un filet, jamais par une gouttière. Les écrans secondaires (liste des instances, bibliothèque, journal, paramètres) utilisent une page centrée de 1680 px au plus, avec 16 px de marge et des panneaux empilés qui partagent leur bordure.

**Dimensions.** Barre 52 px ; en-tête de panneau, bouton et lien de menu 40 px ; onglet 36 px ; petit bouton, champ et ligne haute 32 px ; titre de colonnes et choix segmenté 26 px ; très petit bouton 24 px ; ligne de données 22 px ; cible tactile 44 px.

**Espacements.** Marge intérieure d'un panneau : 12 px. Marge intérieure d'une cellule de tableau : 10 px. Écart entre deux groupes dans une barre : 14 px. Marge de page et de barre du haut : 16 px. Écarts serrés entre éléments liés : 2, 4, 6 et 8 px. Marge intérieure des boutons : 18 px (12 px en petit, 8 px en très petit).

**Tablette.** Sous 1100 px, l'écran d'une instance défile : la bande d'indicateurs passe sur deux rangées avec un défilement horizontal, la grille devient une colonne (composition repliable, puis graphique de 440 px, puis journal de 380 px), et les grilles de réglages passent de quatre à deux colonnes. La navigation de la barre du haut se replie dans un bouton « Menu ». Le bandeau des instances disparaît sous 980 px, l'état des bots sous 640 px. Avec un pointeur tactile, toute cible fait au moins 44 px de haut.

### Named Rules

**La règle des hauteurs comptées.** Une hauteur se choisit dans la série 22, 26, 32, 36, 40, 52 px. On compose avec ces valeurs, on n'en invente pas d'autres.

**La règle du filet partagé.** Deux panneaux voisins partagent un seul filet de 1 px. Pas de gouttière, pas de carte isolée.

## Elevation & Depth

Le système est entièrement à plat. Il n'y a aucune ombre portée. La profondeur se lit par trois tons de fond (fond, panneau, surface relevée) et deux tons de filet. Un panneau flottant (infobulle, détail du solde, menu) se distingue par son fond relevé et son contour en filet fort, pas par une ombre. Le fond d'une boîte de dialogue est le fond de page à 78 % d'opacité.

La propriété `box-shadow` n'est utilisée qu'en mode incrusté, pour tracer un trait de sélection de 2 px à l'intérieur d'un élément : en haut d'un onglet ou d'un choix segmenté, en bas d'un lien de navigation, à gauche d'une ligne. Ce trait est ambre pour la sélection, bleu pour la ligne choisie dans le journal, rouge pour une ligne en alerte.

### Named Rules

**La règle du plat.** Aucune ombre portée, aucun flou, aucun dégradé de surface. Un niveau se dit par un ton de fond et un filet.

**La règle du trait de 2 px.** L'élément sélectionné porte un trait plein de 2 px sur un seul bord, à l'intérieur de sa boîte. C'est le seul marqueur de sélection.

## Shapes

Tout est rectangulaire. Les panneaux, les étiquettes, les lignes et les panneaux flottants ont des coins vifs (0). Les éléments que l'on manipule (boutons, champs, choix segmentés, boîtes de dialogue, infobulle du graphique) ont un coin à peine adouci (2 px). Aucune pastille, aucun cercle.

Les bordures font 1 px. Leur style porte un sens : trait plein pour ce qui est réel ou constaté, pointillés pour ce qui est simulé, en attente ou indisponible (mention « simulé », mode test, commande en attente, étape en cours, option verrouillée, avertissement).

Les icônes sont rares et dessinées en SVG au trait ou en aplat, dans la couleur du texte : la flèche de variation (triangle de 8 px), le cadenas d'une option verrouillée. Le carré bleu de 6 px marque une unité de temps que le bot trade réellement.

### Named Rules

**La règle du pointillé.** Un contour en pointillés veut dire « pas réel » ou « pas encore » : simulé, en attente, verrouillé. Il ne s'emploie pas comme décor.

## Components

Des pièces de terminal : plates, serrées, bordées d'un filet, et qui ne bougent que lorsque quelque chose a changé.

### Buttons
- **Shape:** rectangle à coin de 2 px, bordure de 1 px, 40 px de haut ; 32 px en petit, 24 px en très petit ; 44 px au minimum au doigt.
- **Par défaut :** fond transparent, contour en filet fort, texte os. Au survol, le contour passe au gris moyen.
- **Principal :** fond ambre, texte encre d'ambre. Un seul par écran ou par dialogue. Au survol, ambre clair.
- **Danger :** contour et texte rouges, fond transparent ; au survol, fond rouge à 16 %. Sert aux commandes qui vendent ou arrêtent.
- **Discret :** sans contour, texte gris moyen ; au survol, texte os et contour.
- **En attente :** contour ambre en pointillés et fond ambre à 10 % tant que l'effet de la commande n'est pas constaté.
- **Enfoncé (préréglage choisi) :** contour ambre doublé d'un trait intérieur.
- **Désactivé :** opacité 0,45.
- **Hover / Focus :** transition de 150 ms sur le fond, le contour et le texte. Focus au clavier : contour ambre de 1 px, décalé de 3 px, sur tout élément.

### Chips
- **Étiquette :** bordure de 1 px dans la couleur du texte, coins vifs, Martian Mono 11 px. Sert aux faits courts : « test », « simulé », âge d'une donnée.
- **Mention « simulé » :** contour ambre en pointillés, texte ambre en capitales. Obligatoire à côté de tout chiffre du mode test ou d'un backtest.
- **Étiquette de mode :** test en ambre pointillé, backtest en violet à trait plein, réel en fond rouge plein avec texte couleur de fond et graisse 700.
- **Variation signée :** une flèche SVG de 8 px, le signe et le pourcentage, en vert, rouge ou bleu. Une variation nulle est grise et sans flèche.

### Cards / Containers
- **Panneau :** fond panneau, bordure de 1 px, coins vifs, aucune ombre. En-tête de 40 px avec un filet dessous ; pied facultatif en 12 px gris.
- **Titres de colonnes :** bande de 26 px, libellés en capitales, filet dessous.
- **Ligne de données :** 22 px, grille de colonnes, texte tronqué par des points de suspension, filet adouci dessous ; 32 px en version haute. La ligne survolée ou sélectionnée prend le fond relevé.
- **Barre de chaleur :** aplat à 16 % derrière un chiffre, voir Colors.
- **Liste clé / valeur :** deux colonnes en Martian Mono 11 px, la clé en gris, la valeur alignée à droite.
- **Bandeau d'avertissement :** contour ambre en pointillés et texte ambre ; contour rouge plein pour une erreur.
- **État vide :** texte gris centré de 13 px qui dit ce qui manque et ce qu'il faut faire.
- **Valeur périmée :** opacité 0,5, toujours avec son âge affiché à côté.

### Inputs / Fields
- **Style:** 32 px de haut, fond de page, contour en filet fort, coin de 2 px, texte de 13 px (Martian Mono 12 px pour un nombre). Libellé gris au-dessus, aide ou erreur en 12 px dessous.
- **Focus:** contour ambre de 1 px décalé de 3 px. Survol : contour gris moyen.
- **Error / Disabled:** message rouge sous le champ, annoncé aux lecteurs d'écran. Case à cocher et curseur teintés d'ambre.
- **Choix à options décrites :** une boîte bordée par option, avec un titre et une ligne d'explication ; l'option choisie a un contour ambre doublé ; l'option indisponible est en pointillés avec un cadenas.

### Navigation
- **Barre du haut :** 52 px, collante, fond de page à 94 % d'opacité, filet dessous. Liens de 13 px en gris moyen ; la page courante est en os avec un trait ambre de 2 px en bas.
- **Onglets :** 36 px, 13 px en graisse 600, séparés par un filet vertical. L'onglet actif prend le fond panneau et un trait ambre de 2 px en haut, qui glisse d'un onglet à l'autre.
- **Choix segmenté :** boutons de 26 px accolés (Observation / Réglages, unités de temps) ; le bouton actif prend le fond relevé et le trait ambre en haut.
- **Tablette :** les liens se replient dans un panneau « Menu » ; chaque lien y fait 40 px, la page courante porte le trait ambre à gauche.

### Boîte de dialogue
Élément `<dialog>` natif : 560 px de large (820 px en version large), fond panneau, contour en filet fort, coin de 2 px, en-tête de 40 px avec un bouton « Fermer », corps en grille avec 14 px d'écart, pied aligné à droite.

### Infobulle de vocabulaire
Un mot courant souligné en pointillés. Au survol ou au focus, un panneau relevé de 280 px au plus donne le terme technique en Martian Mono, puis l'explication. La touche Échap le referme.

### Séquence de démarrage
Trois étapes reliées par un filet : Lancement, Vérification, Actif. Chaque étape a un carré de 14 px : vide au départ, contour bleu en pointillés quand elle est en cours, rempli de vert quand elle est constatée, contour et fond rouges quand elle échoue, avec la cause écrite à côté.

### Bande d'indicateurs
Le solde en Martian Mono 21 px avec ses deux variations : l'encaissé en vert ou rouge, l'en cours en bleu, chacune avec son mot. À sa droite, les indicateurs sur trois rangées de 22 px, libellé à gauche et valeur à droite. Un clic sur le solde ouvre son détail.

### Graphique de trading
Bougies sur fond panneau, grille à 18 % du filet, échelles en Martian Mono 11 px. Les marqueurs d'achat et de vente sont bleus et portent leur mot. Entre l'achat et la vente : une zone verte ou rouge à 15 % (26 % si sélectionnée), la portion de courbe en bleu sur 2 px, et une étiquette de résultat. Deux lignes en tirets par position : vente à gain en vert, vente à perte en rouge, chacune avec son libellé et son prix. Une étiquette donne l'âge de la donnée ; un graphique périmé passe à 45 % d'opacité.

### Journal des transactions
Lignes de 22 px sur trois colonnes : heure, événement, montant. Les nouvelles lignes arrivent par le bas. Une vente porte une barre de chaleur verte ou rouge, un achat refusé une bande hachurée, une alerte un fond ambre à 8 %. La ligne choisie prend le fond relevé et un trait bleu à gauche.

### Bandeau d'arrêt d'urgence
Une bande hachurée ambre sous la barre du haut, avec un filet ambre dessous. Elle dit ce qui est bloqué et ce qui continue, et porte le bouton qui lève l'arrêt.

### Mouvement
Chaque animation montre un changement réel. Aucune ne tourne en boucle ni ne sert de décor. La courbe de référence est `cubic-bezier(0.2, 0.8, 0.2, 1)`.

- Changement d'état d'une commande (fond, contour, texte) : 150 ms.
- Ouverture d'un panneau flottant : 150 ms, opacité et 6 px de glissement.
- Changement d'écran : 160 ms, opacité et 4 px.
- Étape de démarrage constatée : remplissage du carré en 180 ms, puis du filet en 200 ms.
- Bascule entre observation et réglages : 200 ms, opacité et 24 px de glissement latéral.
- Graphique périmé : 200 ms d'opacité.
- Trait de l'onglet actif : 220 ms de glissement.
- Ajout ou retrait d'une ligne de réglage : 200 à 220 ms.
- Barre de progression : 250 ms.
- Nouvelle ligne du journal : 280 ms, opacité et 12 px de montée.
- Apparition de la zone d'une transaction terminée sur le graphique : 350 ms.
- Chiffre qui défile vers sa nouvelle valeur : 400 ms. C'est la durée la plus longue du système.

Avec `prefers-reduced-motion`, toutes les transitions et animations sont coupées : les chiffres changent d'un coup, les étapes constatées s'affichent déjà remplies, le graphique se dessine sans effet.

## Do's and Don'ts

### Do:
- **Do** lire les couleurs par leurs rôles `--c-*`, pour que le thème clair et la personnalisation continuent de fonctionner.
- **Do** accompagner chaque couleur de sens d'un signe, d'une flèche ou d'un libellé. En vision daltonienne, le vert et le rouge de la référence ne sont séparés que de 6 à 8 points.
- **Do** écrire tout nombre en Martian Mono, avec chiffres tabulaires, signe explicite et devise.
- **Do** composer avec les hauteurs 22, 26, 32, 36, 40 et 52 px et la marge de panneau de 12 px.
- **Do** coller les panneaux et les séparer par un filet de 1 px.
- **Do** poser la mention « simulé » en pointillés ambre à côté de tout chiffre du mode test ou d'un backtest.
- **Do** garder le mode réel comme seule étiquette à fond plein.
- **Do** donner au moins 44 px de haut à toute cible tactile.
- **Do** garder chaque animation sous 400 ms environ, liée à un changement réel, et coupée avec `prefers-reduced-motion`.
- **Do** vérifier chaque nouvelle teinte dans les deux thèmes : 4,5:1 pour du texte, 3:1 pour un repère graphique.

### Don't:
- **Don't** construire un tableau de bord aéré fait de cartes séparées par des gouttières. La maquette est un terminal dense.
- **Don't** ajouter une ombre portée, un flou ou un dégradé de surface. Le trait intérieur de 2 px reste le seul usage de `box-shadow`.
- **Don't** arrondir au-delà de 2 px, ni dessiner de pastille ou de cercle.
- **Don't** utiliser le vert, le rouge, le bleu, l'ambre ou le violet comme décor ou hors de leur sens.
- **Don't** utiliser le bleu pour un résultat encaissé, ni le vert ou le rouge pour un résultat encore en cours.
- **Don't** employer le pointillé pour autre chose que le simulé, l'attente ou l'indisponible.
- **Don't** poser un petit libellé en capitales au-dessus d'un titre comme ornement. Ce style nomme une donnée.
- **Don't** introduire une troisième police, ni une taille de texte hors de 11, 12, 12,5, 13, 14, 15 et 21 px.
- **Don't** animer en boucle ni animer un élément dont la valeur n'a pas changé.
- **Don't** charger une police, une icône ou un script depuis un serveur tiers.
