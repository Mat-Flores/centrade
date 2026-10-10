---
name: Centrade
description: Un tableau d'instruments pour gouverner des moteurs de trading, sobre au repos, sans ambiguïté sous alerte.
colors:
  cobalt-sourd: "oklch(0.46 0.13 250)"
  cobalt-sourd-dark: "oklch(0.78 0.1 245)"
  sur-cobalt: "oklch(0.985 0.004 255)"
  sur-cobalt-dark: "oklch(0.2 0.03 255)"
  anneau-focus: "oklch(0.5 0.15 250)"
  anneau-focus-dark: "oklch(0.78 0.1 245)"
  rouge-alarme: "oklch(0.5 0.19 27)"
  rouge-alarme-dark: "oklch(0.7 0.17 25)"
  sur-alarme: "oklch(0.985 0.004 255)"
  sur-alarme-dark: "oklch(0.2 0.03 255)"
  brume-froide: "oklch(0.975 0.005 255)"
  brume-froide-dark: "oklch(0.195 0.014 255)"
  nuit-bleutee: "oklch(0.24 0.025 255)"
  nuit-bleutee-dark: "oklch(0.94 0.008 255)"
  brume-panneau: "oklch(0.995 0.003 255)"
  brume-panneau-dark: "oklch(0.235 0.016 255)"
  brume-sourde: "oklch(0.945 0.008 255)"
  brume-sourde-dark: "oklch(0.285 0.016 255)"
  texte-secondaire: "oklch(0.46 0.022 255)"
  texte-secondaire-dark: "oklch(0.74 0.016 255)"
  filet: "oklch(0.88 0.01 255)"
  filet-dark: "oklch(0.35 0.016 255)"
  contour-champ: "oklch(0.58 0.02 255)"
  contour-champ-dark: "oklch(0.62 0.022 255)"
typography:
  headline:
    fontFamily: "Hanken Grotesk Variable, ui-sans-serif, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.333
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Hanken Grotesk Variable, ui-sans-serif, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Hanken Grotesk Variable, ui-sans-serif, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum"
  label:
    fontFamily: "Hanken Grotesk Variable, ui-sans-serif, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.375
  support:
    fontFamily: "Hanken Grotesk Variable, ui-sans-serif, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.43
  data:
    fontFamily: "Geist Mono Variable, ui-monospace, monospace"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
  xl: "12px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "10": "40px"
components:
  button-primary:
    backgroundColor: "{colors.cobalt-sourd}"
    textColor: "{colors.sur-cobalt}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    height: "44px"
    padding: "0 16px"
  button-primary-hover:
    backgroundColor: "oklch(0.46 0.13 250 / 0.8)"
  button-primary-lg:
    backgroundColor: "{colors.cobalt-sourd}"
    textColor: "{colors.sur-cobalt}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    height: "48px"
    padding: "0 20px"
  input:
    backgroundColor: "{colors.brume-froide}"
    textColor: "{colors.nuit-bleutee}"
    typography: "{typography.data}"
    rounded: "{rounded.lg}"
    height: "44px"
    padding: "4px 12px"
  alert:
    backgroundColor: "{colors.brume-panneau}"
    textColor: "{colors.nuit-bleutee}"
    typography: "{typography.support}"
    rounded: "{rounded.lg}"
    padding: "12px"
  panel:
    backgroundColor: "{colors.brume-panneau}"
    textColor: "{colors.nuit-bleutee}"
    rounded: "{rounded.xl}"
    padding: "24px"
    width: "384px"
---

# Design System: Centrade

<!-- État au jalon M0 : un seul écran existe (Connexion). Ce fichier décrit ce qui est livré dans `apps/web/src/index.css` et `apps/web/src/components/ui/`. Relancer `/impeccable document` quand le Cockpit (M1) apporte tableaux, badges et navigation. -->

## Overview

**Creative North Star: "Le tableau d'instruments"**

Centrade se lit comme un panneau de mesures : chaque valeur est à sa place, lue et datée, et rien ne bouge sans raison. Tant que tout va bien, l'écran est calme, presque monochrome : des gris froids teintés de bleu, un seul bleu d'accent pour l'action principale, des chiffres alignés. Quand quelque chose ne va pas, c'est le contenu qui change (un mot, un contour, une couleur réservée), pas le décor.

Les composants sont retenus à l'œil et francs sous le doigt. Au repos : bords nets, aucun effet, aucune ombre sauf celle du panneau. À l'action : cibles de 44 à 48 px, retour immédiat (120 ms), anneau de focus opaque de 2 px. Le même écran sert le coup d'œil, la session longue au bureau et l'arrivée sur alerte depuis une tablette.

Le système est un socle shadcn (style `radix-nova`) réduit à ce que les jetons permettent : toute couleur, tout rayon, toute ombre et toute durée vient de `apps/web/src/index.css`. Les deux thèmes dérivent des mêmes jetons et suivent le réglage du système.

**Key Characteristics:**

- Gris teintés (teinte 255), jamais de noir ni de gris purs.
- Un seul accent, le Cobalt sourd ; le Rouge alarme est réservé au mode LIVE et au danger.
- Hiérarchie par taille et graisse, pas par couleur.
- Chiffres tabulaires partout ; chasse fixe pour ce qui se saisit ou se compare.
- Plat par défaut : une seule ombre, celle du panneau.
- Cibles d'au moins 44 px, focus toujours visible, mouvement réduit respecté.

## Colors

Une palette froide et presque neutre : deux gris de brume pour les surfaces, une nuit bleutée pour le texte, un cobalt pour agir. Les valeurs sont dans l'en-tête, en OKLCH, avec leur pendant sombre (`-dark`).

### Primary

- **Cobalt sourd** (`cobalt-sourd`, jeton CSS `--primary`) : le fond de l'action principale d'un écran (« Se connecter ») et la teinte de la sélection de texte (à 30 %). Rien d'autre. En thème sombre il s'éclaircit et le texte posé dessus devient sombre (`sur-cobalt-dark`).
- **Anneau de focus** (`anneau-focus`, `--ring`) : un cobalt un peu plus vif, réservé au contour de focus clavier.

### Secondary

- **Rouge alarme** (`rouge-alarme`, `--live` et `--destructive`) : mode LIVE et états dangereux. Déclaré dans les jetons, encore absent de l'écran livré : c'est voulu. Ce n'est pas un second accent, c'est un signal.

### Neutral

- **Brume froide** (`brume-froide`, `--background`) : fond de page et fond des champs de saisie.
- **Brume panneau** (`brume-panneau`, `--card`) : surface des panneaux et des alertes, un cran plus claire que la page (plus claire aussi en thème sombre).
- **Brume sourde** (`brume-sourde`, `--muted`) : fond de survol des boutons discrets.
- **Nuit bleutée** (`nuit-bleutee`, `--foreground`) : tout le texte principal ; aussi le contour d'un champ en erreur.
- **Texte secondaire** (`texte-secondaire`, `--muted-foreground`) : sous-titres, aides, pied de page.
- **Filet** (`filet`, `--border`) : contours de panneaux et séparateurs, à peine visibles.
- **Contour de champ** (`contour-champ`, `--input`) : contour des champs, nettement plus marqué que le filet pour qu'un champ se reconnaisse sans son étiquette (contraste d'au moins 3:1).

### Named Rules

**Règle du rouge réservé.** Le rouge ne décore jamais. Il dit « LIVE » ou « danger », et rien d'autre. Une erreur de saisie ou de connexion n'est pas un danger : elle s'écrit en Nuit bleutée, avec une icône et un texte qui donne la cause et l'action possible.

**Règle de l'accent unique.** Un seul élément en Cobalt sourd plein par vue : l'action principale. Sa rareté fait qu'on le trouve sans chercher.

**Règle du gris teinté.** Aucune couleur en dur dans un composant, aucun `#000`, aucun `#fff`, aucun gris sans teinte. Tout passe par un jeton.

## Typography

**Display Font:** aucune. La même famille sert les titres et le texte.
**Body Font:** Hanken Grotesk Variable (repli `ui-sans-serif, sans-serif`)
**Label/Mono Font:** Geist Mono Variable (repli `ui-monospace, monospace`)

**Character:** Une grotesque ronde et lisible pour parler, une chasse fixe étroite pour mesurer. Les deux sont auto-hébergées (`@fontsource-variable`), aucune ressource tierce.

### Hierarchy

- **Headline** (600, 1.5rem, interlettrage -0.025em) : le nom du produit en tête d'écran.
- **Title** (600, 1.25rem, interlettrage -0.025em) : le titre d'un panneau (« Connexion »).
- **Body** (400, 1rem, interligne 1.5) : texte courant et libellé des boutons (500 sur un bouton).
- **Label** (500, 0.875rem) : étiquettes de champ, titres d'alerte.
- **Support** (400, 0.875rem, Texte secondaire) : sous-titres, descriptions d'alerte, pied de page.
- **Data** (Geist Mono, 400, 1rem) : tout ce que l'opérateur saisit ; à étendre aux identifiants, prix et horodatages.

### Named Rules

**Règle des chiffres alignés.** `font-variant-numeric: tabular-nums` est posé sur `html` : tout chiffre s'aligne, même en Hanken Grotesk. La chasse fixe s'ajoute pour ce qui se compare colonne à colonne ou se recopie.

**Règle taille et graisse.** On hiérarchise par taille (1.5 / 1.25 / 1 / 0.875rem) et par graisse (600 / 500 / 400). La couleur ne distingue que deux niveaux de texte : principal et secondaire.

## Layout

Unité de base de 4 px (`--spacing: 0.25rem`) ; les pas observés sont 8, 12, 16, 20, 24, 32 et 40 px.

L'écran livré est une colonne pleine hauteur (`min-h-dvh`) en trois bandes : le nom du produit en haut à gauche, le contenu centré, la mention légale en bas à gauche. Marge de page de 16 px (haut et bas 24 px), qui passe à 40 px (32 px) à partir de 640 px. Le panneau de connexion est limité à 384 px de large, avec 24 px de marge intérieure, 32 px à partir de 640 px.

Rythme dans un formulaire : 8 px entre une étiquette et son champ, 16 px entre deux champs, 20 px entre les blocs (champs, message, bouton), 24 px sous l'en-tête du panneau.

Les captures de référence couvrent 1280 × 800 (bureau) et 820 × 1180 (tablette), en clair et en sombre.

## Elevation & Depth

Plat par défaut. La profondeur vient d'abord du ton : le panneau est un cran plus clair que la page et porte un filet. Une seule ombre existe, douce et teintée, pour détacher ce panneau du fond.

### Shadow Vocabulary

- **Panneau** (`--elevation-panel`, utilitaire `shadow-panel` : `0 1px 2px oklch(0.24 0.025 255 / 0.06), 0 4px 16px oklch(0.24 0.025 255 / 0.05)` ; en sombre `0 1px 2px oklch(0.1 0.02 255 / 0.4), 0 4px 16px oklch(0.1 0.02 255 / 0.3)`) : un panneau posé directement sur le fond de page.

### Named Rules

**Règle de l'ombre unique.** Boutons, champs et alertes n'ont pas d'ombre, ni au repos ni au survol. Un panneau dans un panneau n'existe pas.

## Shapes

Des angles doucement arrondis, dérivés d'un seul rayon (`--radius: 0.5rem`) : 8 px pour les contrôles (boutons, champs, alertes), 12 px pour les panneaux, 6 px et 4 px pour les petits éléments. Les contours font 1 px. Aucune pastille, aucun cercle décoratif, aucune bordure latérale colorée.

L'anneau de focus est la seule forme qui déborde : contour opaque de 2 px, décalé de 2 px par un liseré de la couleur du fond, pour rester lisible sur toute surface.

## Components

Seuls les composants visibles sur l'écran livré sont décrits. `Label`, `Field`, `Separator` et `Spinner` sont des éléments de structure sans caractère propre.

### Buttons

Sobres au repos, francs à la pression.

- **Shape:** angles doucement arrondis (8 px), contour transparent de 1 px.
- **Primary:** fond Cobalt sourd, texte Sur-cobalt, 1rem en graisse 500. Hauteur 44 px (marge latérale 16 px) ; 48 px (20 px) en taille `lg`, celle du bouton d'envoi d'un formulaire.
- **Hover / Focus:** au survol le fond passe à 80 % d'opacité ; à la pression le bouton descend de 1 px ; au focus, anneau de 2 px décalé de 2 px. Transition de couleur seulement, 120 ms, `cubic-bezier(0.22, 1, 0.36, 1)`.
- **Pending / Disabled:** opacité 50 %, clics ignorés ; pendant un envoi, une icône tournante de 16 px précède un libellé qui dit ce qui se passe (« Connexion en cours… »).
- **Autres variantes :** `outline`, `ghost`, `destructive` et `link` existent dans le fichier shadcn mais ne sont employées sur aucun écran. La variante `secondary` référence un jeton `--secondary` qui n'existe pas : ne pas l'employer tant qu'il n'est pas défini. Les tailles `xs`, `sm` et `icon*` (24 à 36 px) sont sous le seuil de 44 px : pas sur une cible tactile.

### Cards / Containers

- **Corner Style:** 12 px.
- **Background:** Brume panneau sur fond Brume froide.
- **Shadow Strategy:** l'ombre Panneau, la seule du système.
- **Border:** Filet de 1 px.
- **Internal Padding:** 24 px, 32 px à partir de 640 px.

### Inputs / Fields

- **Style:** hauteur 44 px, angles de 8 px, fond Brume froide (en creux par rapport au panneau), contour de 1 px en Contour de champ, texte en Geist Mono 1rem. Étiquette au-dessus, en Label.
- **Focus:** le contour prend la couleur de l'anneau, plus l'anneau de 2 px décalé.
- **Error / Disabled:** en erreur, le contour passe en Nuit bleutée (pas en rouge) et le champ pointe vers le message par `aria-describedby` ; désactivé, opacité 60 % et curseur interdit.

### Alerts

Un seul style pour l'échec et la réussite : la différence est dans l'icône et le texte.

- **Style:** angles de 8 px, fond Brume panneau, contour de 1 px en Nuit bleutée à 40 %, marge intérieure 12 px. Icône de 16 px à gauche, titre en Label, description en Support.
- **Contenu:** le titre nomme le fait (« Connexion impossible »), la description donne la cause et l'action possible.

### Navigation

Pas encore de navigation : l'écran livré ne porte que le nom du produit en Headline. La barre persistante du `SPEC.md` §9 arrive au jalon M1.

## Do's and Don'ts

### Do:

- **Do** prendre toute couleur, tout rayon, toute ombre et toute durée dans `apps/web/src/index.css`, par les utilitaires Tailwind qui en découlent (`bg-primary`, `rounded-lg`, `shadow-panel`).
- **Do** garder un seul élément en Cobalt sourd plein par vue.
- **Do** donner au moins 44 px de haut à tout contrôle (bouton par défaut, champ), 48 px à l'action principale d'un formulaire.
- **Do** écrire en Geist Mono ce qui se saisit ou se compare : identifiants, prix, quantités, horodatages.
- **Do** dire une erreur par un contour Nuit bleutée, une icône et un texte « cause, puis action possible ».
- **Do** vérifier chaque écran dans les deux thèmes, à 1280 px et à 820 px, avec `axe` sans violation.
- **Do** garder l'anneau de focus opaque de 2 px, décalé de 2 px, sur tout élément interactif.

### Don't:

- **Don't** employer le Rouge alarme hors du mode LIVE et des états dangereux, ni le vert ou le rouge de PnL comme décoration.
- **Don't** ajouter de dégradé décoratif, d'ombre lourde, de carte dans une carte, ni d'icône dans une pastille au-dessus d'un titre.
- **Don't** écrire une couleur en dur dans un composant, ni du noir ou un gris pur.
- **Don't** choisir Inter, Arial ou une police système, ni charger une police, un script ou un style depuis un tiers.
- **Don't** hiérarchiser par la couleur ce qui peut l'être par la taille ou la graisse.
- **Don't** animer autre chose que la couleur d'un état, ni au-delà de 120 ms ; `prefers-reduced-motion` coupe tout.
- **Don't** employer la variante de bouton `secondary` tant que le jeton `--secondary` n'existe pas.
