# Product

<!-- impeccable:product-schema 1 -->

Brouillon pour la maquette `maquettes/rework-ui/`. Il ne remplace pas le `PRODUCT.md` de la racine : seul l'opérateur le fera, avec `/impeccable init`. `SPEC.md` reste la source de vérité ; les écarts décidés ici sont consignés dans `ECARTS-SPEC.md`.

## Platform

web

## Users

Un opérateur unique, qui fait tourner ses propres bots de trading et en assume seul les risques. Il connaît le trading, mais veut une interface qui parle simplement.

Scène principale : un écran de bureau allumé pendant des heures, souvent le soir ou à côté d'autre chose. Scène secondaire, à ne pas négliger : des coups d'œil courts en journée, dans une pièce claire ou sur tablette. Le thème sombre est soigné en premier ; le thème clair doit rester aussi lisible.

## Product Purpose

Centrade gouverne des bots de trading (Freqtrade en V1) : il les règle, les borne, les surveille et montre ce qu'ils font réellement. Il ne décide d'aucun trade et n'émet aucun ordre.

La refonte organise tout autour de l'**instance** : un environnement, dans un mode (test, réel ou backtest), avec un compte, des paires et une stratégie affectée à chaque paire. On la règle à l'arrêt, on l'observe en marche.

Le produit est réussi quand l'opérateur voit en quelques secondes ce que son instance a gagné ou perdu, pourquoi, et ce qu'elle fait en ce moment, sans jamais être trompé sur ce qui est réel.

## Positioning

Complet sur le fond, simple dans les mots. Toute l'information de trading est là ; les libellés sont en langage courant et le terme technique reste à portée d'infobulle. Ce qui est affiché est observé et daté, jamais supposé.

Ce n'est ni un moteur de trading, ni un outil pour concevoir une stratégie rentable, ni un conseil financier.

## Operating Context

- Deux entrées principales : **Instances** (liste, puis vue d'une instance) et **Bibliothèque** (clés, stratégies, automatisations). Journal et Paramètres restent à part ; Flow et Agents passent dans un menu « Avancé ».
- Vue d'une instance en marche (observation) :
  - bande d'onglets en haut, « Tout » à gauche puis un onglet par paire ;
  - à gauche du graphique, un panneau qui montre les stratégies et le compte utilisés, et quelles paires partagent quelle stratégie ;
  - au centre, le graphique de trading ;
  - à droite, le journal des transactions, à défilement infini, les nouvelles lignes arrivant par le bas ;
  - les indicateurs, sur le même panneau.
- Vue d'une instance à l'arrêt, toutes les ventes terminées (paramétrage) : on ajoute, modifie et règle paires, stratégies, compte et automatisations. Chaque modification crée une nouvelle version, visible dans un historique.
- Instance en mode backtest : même paramétrage, puis « Importer les données » et « Démarrer la simulation » à la place de « Démarrer ».
- Bureau à 1280 px et tablette. Accès par VPN uniquement.

## Capabilities and Constraints

**Modèle d'une instance.** Un mode, fixé à la création (test ou backtest). Un seul compte. Des paires ; chaque paire a une stratégie, et plusieurs paires peuvent partager la même. En coulisse : un bot par stratégie.

**Passage en réel.** Le mode réel ne se choisit pas à la création. Une instance en mode test porte « Passer en réel » : liste de contrôles, code TOTP, puis une copie réelle est créée. Une instance réelle modifiée repasse par le mode test.

**Démarrage.** Trois étapes visibles : Lancement, Vérification, Actif. Chaque étape n'est cochée que lorsqu'elle est observée ; une étape bloquée dit pourquoi.

**Automatisations** (créées dans la Bibliothèque, rattachées à une instance) : alertes et notifications ; règles de protection (elles ne peuvent que réduire le risque) ; planification ; agents IA (ils proposent, un humain valide).

**Solde.** « 2 000,00 USDT ▲ +10,00 % », sans le mot « hausse ». Deux variations distinctes : le résultat encaissé (transactions terminées), en vert ou en rouge ; la variation en cours, en bleu, qui tient compte des transactions ouvertes. Le clic ouvre un panneau de détail : départ, gains encaissés, gains en cours, frais, total. Montants dans la devise du compte, jamais convertis.

**Indicateurs.** Tous activables un par un ; les importants sont actifs par défaut. Quatre groupes :

- Performance : taux de réussite, gain moyen, perte moyenne, rapport gains/pertes, meilleur et pire trade, espérance par trade, ratios de Sharpe, Sortino et Calmar.
- Risque : plus forte baisse depuis un sommet, baisse en cours, part du capital engagée, distance au stop des positions ouvertes.
- Activité : positions ouvertes, durée moyenne d'un trade, frais payés, achats refusés par les protections.
- Causes de vente : objectif atteint, stop, stop suiveur, signal de la stratégie, délai, manuel, arrêt d'urgence.

**Graphique.** Bougies. Marqueurs d'achat et de vente en bleu. Entre l'achat et la vente : une zone verte ou rouge, la portion de courbe en bleu, et une étiquette de résultat légèrement détachée de la courbe. Deux lignes tracées pour chaque position : stop-loss et take-profit. Unités de temps modifiables ; celles que le bot trade réellement sont mises en évidence.

**Backtest.** Une période et un jeu de coûts (frais, glissement) pour toute l'instance. Chaque onglet de paire indique l'état de ses données pour l'unité de temps tradée : complètes, partielles ou absentes. La simulation affiche sa progression, puis le résultat complet, avec un bouton lecture et un curseur de temps pour rejouer la période en accéléré. Mention permanente : « un backtest n'est pas une prévision ».

**Couleurs.** Vert pour un gain, rouge pour une perte, bleu pour les achats, les ventes et ce qui est en cours. Chaque mode a sa couleur. La couleur ne porte jamais seule le sens : signe, flèche ou libellé à côté. Toutes les couleurs significatives sont personnalisables : préréglages (classique, adapté au daltonisme, inversé) et réglage libre, avec un avertissement quand deux couleurs deviennent trop proches ou peu lisibles.

**Vocabulaire.** Mots courants, terme technique en infobulle. Ne pas traduire ce qui est déjà courant en français : bot, trade, backtest, stop-loss, take-profit, live restent tels quels. Table de correspondance dans `VOCABULAIRE.md`.

**Mouvement.** Expressif mais utile, jusqu'à 400 ms environ : chiffres qui défilent, graphique qui se trace, lignes du journal qui glissent, transitions entre onglets et entre observation et paramétrage. Chaque animation montre un changement réel. `prefers-reduced-motion` respecté.

**Règles de vérité de l'affichage** (inchangées, `SPEC.md` §9) :

- état voulu et état observé visibles ; rien n'est « fait » avant d'être observé ;
- chaque valeur est datée ; une valeur périmée est estompée et marquée ;
- les chiffres du mode test et du backtest portent « simulé » ; réel, test et backtest ne s'additionnent jamais ;
- arrêter, vendre ou mettre en pause n'est jamais bloqué ni caché ;
- signe toujours explicite sur un résultat, devise toujours affichée ;
- nombres au format `fr-CA`, heure de Toronto avec le fuseau indiqué ;
- aucune ressource tierce : polices et scripts servis en local.

**Hors périmètre :** émission d'ordres par la plateforme, conception de stratégies rentables, levier, vente à découvert, produits dérivés, multi-utilisateurs, application mobile.

## Brand Commitments

- **Nom :** Centrade.
- **Identité visuelle :** fixée par l'opérateur le 12 octobre 2026. La maquette reprend exactement les couleurs, la rigueur d'espacement, les dimensions et l'optimisation de l'espace de la page de référence (https://impeccable.style/gallery/view/b5850eeea1c2e703/) : fond presque noir, filets d'un pixel, panneaux à plat, lignes de 22 px, chiffres à chasse fixe, titres condensés en capitales, ambre pour l'action principale et les avertissements. Jetons dans `src/theme/tokens.css`. Deux ajouts absents de la référence : un bleu pour les achats, les ventes et ce qui est en cours, et un thème clair.
- **Logo :** aucun. À ne pas inventer sans demande.
- **Ton :** neutre, à l'infinitif, sans tutoiement ni vouvoiement (« Arrêter l'instance », « Aucune position ouverte »). Un message d'erreur donne la cause et l'action possible.

## Evidence on Hand

- `SPEC.md`, `docs/invariants.md`.
- Aucune donnée de trading réelle, aucun chiffre de performance, aucun témoignage. Les données de la maquette sont inventées, déterministes et marquées « simulé ».
- Référence visuelle fournie par l'opérateur : https://impeccable.style/gallery/view/b5850eeea1c2e703/ (une interface d'exchange de produits perpétuels). C'est une inspiration, pas une consigne.

## Product Principles

1. **Le vrai avant le rassurant.** « Inconnu » ou « périmé » plutôt qu'une dernière valeur présentée comme actuelle.
2. **Simple dans les mots, complet sur le fond.** Aucun chiffre utile n'est retiré pour faire simple ; c'est le libellé qui se simplifie.
3. **La couleur a un sens, toujours le même.** Vert, rouge et bleu veulent dire la même chose sur un graphique, un tableau et un indicateur.
4. **Réduire le risque est toujours possible.** Vendre, stopper et mettre en pause ne sont jamais bloqués.
5. **Le réel ne se confond avec rien.** Le mode et le caractère simulé d'un chiffre se lisent sans chercher.
6. **Le mouvement montre ce qui change.** Jamais de décor animé.

## Accessibility & Inclusion

WCAG 2.2 AA. Contraste vérifié dans les deux thèmes, navigation complète au clavier, focus visible, cibles tactiles d'au moins 44 px sur tablette, `prefers-reduced-motion` respecté, préréglage de couleurs adapté au daltonisme.
