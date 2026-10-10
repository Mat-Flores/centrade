# Product

<!-- impeccable:product-schema 1 -->

Source de vérité : `SPEC.md`. Ce fichier en résume ce qui oriente la conception de l'interface ; en cas de conflit, `SPEC.md` gagne.

## Platform

web

## Users

Un opérateur unique, qui fait tourner ses propres moteurs de trading automatisé et en assume seul les risques. Pas de multi-utilisateurs ni de SaaS en V1 ; les rôles `viewer`, `operator` et `admin` existent, mais il n'y a qu'une personne derrière.

Il utilise le dashboard dans trois situations, à parts égales (confirmé par l'opérateur le 10 octobre 2026) :

- **Coups d'œil répétés** dans la journée : savoir en quelques secondes si tout va bien.
- **Sessions longues au bureau** : régler les stratégies, les limites et les politiques, lire les journaux.
- **Sur alerte** : il arrive après une notification Telegram, parfois depuis une tablette ou un téléphone par VPN, et doit comprendre puis agir vite.

## Product Purpose

Centrade centralise la chaîne de trading automatisé de l'opérateur : quelles stratégies tournent, avec quels paramètres et dans quel mode (backtest, paper, live) ; quelles clés et quels comptes ; quelles limites de risque ; et ce que le moteur fait réellement.

C'est une façade de gouvernance au-dessus d'un moteur existant (Freqtrade en V1). Elle règle le moteur, le borne, le surveille et le rend visible. Elle ne décide d'aucun trade et n'émet aucun ordre.

Le produit est réussi quand trois choses sont vraies : ce qu'il affiche est vrai, ce qu'il commande est effectivement appliqué, et sa propre panne ne met aucune position en danger.

## Positioning

Centrade montre l'état observé et daté, jamais l'état supposé. Une valeur trop ancienne est marquée périmée, un état inconnu s'affiche « inconnu », et une commande n'est « faite » que lorsque son effet est observé dans le moteur. Ces garanties sont les quatorze invariants I1 à I14 du `SPEC.md` §1.2 : chacune a un test automatisé, et celles qui s'observent à l'exécution sont surveillées en continu dans le panneau « Garanties ».

Ce n'est ni un moteur de trading, ni un outil de conception de stratégies, ni un conseil financier.

## Operating Context

- Accès par VPN (Tailscale) uniquement ; rien n'est exposé à Internet.
- Bureau à 1280 px et tablette ; consultation possible depuis un téléphone par le VPN. Pas d'application mobile.
- Dix écrans (`SPEC.md` §9) : Cockpit, Stratégies, Ordres et positions, Risque, Comptes et clés, Flow, Agents, Signaux et backtests, Journal et rapports, Paramètres.
- Barre persistante sur tous les écrans : badge de mode, kill switch global, état des connexions, compteurs d'alertes et de propositions, état des garanties, bandeau de mode dégradé.
- Autour du dashboard : notifications Telegram (canal principal) et e-mail, panneaux Grafana intégrés, workflows n8n en périphérie, agents Claude à l'autorité bornée qui soumettent des propositions à valider.
- Les actions dangereuses (passer en live, relever une limite, ajouter une clé, lever un kill switch, assouplir une politique, accepter un risque de protection) exigent une ré-authentification TOTP et une confirmation par saisie.

## Capabilities and Constraints

**Vocabulaire** (glossaire du `SPEC.md` §2, à employer tel quel) : moteur, instance, venue, état voulu, état observé, commande, entrée, sortie, sorties seules, stop protecteur, empreinte de déploiement, kill switch, proposition, bac à sable, invariant.

**Règles de vérité de l'affichage** (`SPEC.md` §9 ; un écran qui les enfreint n'est pas terminé) :

- Chaque valeur issue d'un moteur ou d'une venue donne son âge ; au-delà du seuil de fraîcheur elle est estompée et marquée « périmé depuis … ».
- État voulu et état observé sont montrés côte à côte quand ils diffèrent, avec la commande en cours et son ancienneté.
- Aucun optimisme : un bouton ne passe à « fait » que sur une commande `verified` ; une commande échouée ou expirée reste visible tant qu'elle n'a pas été vue.
- Les chiffres paper, bac à sable et live ne sont jamais additionnés ; tout chiffre paper porte la mention « simulé ».
- Le badge d'une instance montre le mode observé ; un écart s'affiche « MODE INCOHÉRENT ».
- En mode dégradé : bandeau permanent, données estompées, seules les actions qui réduisent le risque restent actives.
- Une boîte de confirmation annonce les conséquences d'après l'état observé à cet instant.

**Contraintes de contenu et de format :**

- Interface en français, textes dans des fichiers de traduction.
- Nombres au format `fr-CA`, signe toujours explicite sur un PnL, devise toujours affichée, précision de l'instrument (aucun arrondi ne masque une perte).
- Horodatages affichés en America/Toronto, fuseau indiqué ; UTC en base.
- Thèmes clair et sombre.
- Le rouge est réservé au mode LIVE et aux états dangereux ; le vert et le rouge de PnL ne servent jamais à décorer.
- Aucune ressource tierce : polices, scripts et styles sont servis par la plateforme, sous une politique de sécurité du contenu stricte.
- Temps réel par SSE.
- Une clé saisie n'est jamais ré-affichée.
- Libellé permanent sur les backtests : « un backtest n'est pas une prévision ».

**Hors périmètre V1 :** trading haute fréquence, multi-utilisateurs, application mobile, conception de stratégies rentables, émission d'ordres par la plateforme, levier, vente à découvert, produits dérivés.

## Brand Commitments

- **Nom :** Centrade (définitif, confirmé par l'opérateur le 10 octobre 2026).
- **Logo et identité visuelle :** aucun pour l'instant. À ne pas inventer sans demande.
- **Ton :** neutre, à l'infinitif, sans tutoiement ni vouvoiement (« Arrêter l'instance », « Aucune position ouverte »). Factuel : un message d'erreur donne la cause et l'action possible.
- **Engagement du `SPEC.md` §9 :** « premium et épuré », un instrument de travail sobre, dense là où il le faut, calme partout ailleurs. Le détail visuel appartient à `DESIGN.md`.

## Evidence on Hand

- `SPEC.md` : exigences, invariants, écrans, scénarios de référence S1 à S14.
- `docs/invariants.md` : chaque invariant, ses tests et son jalon.
- Aucune donnée de trading réelle : l'environnement de développement ne contient que du paper, du dry-run et du bac à sable.
- Aucun témoignage, client, chiffre de performance ni résultat de stratégie. Ne pas en fabriquer : la seule stratégie livrée est un exemple trivial (croisement de moyennes mobiles), et les données de démonstration doivent se lire comme simulées.

## Product Principles

1. **Le vrai avant le rassurant.** Afficher « inconnu » ou « périmé » plutôt qu'une dernière valeur présentée comme actuelle.
2. **Réduire le risque est toujours possible.** Une sortie, un stop ou une fermeture ne sont jamais bloqués ni cachés ; ce qui augmente le risque est refusé en cas de doute.
3. **Dire ce qui va se passer, puis ce qui s'est passé.** Les conséquences sont annoncées avant l'action, et l'effet est constaté après.
4. **Le live ne se confond avec rien.** Mode, environnement et caractère simulé d'un chiffre se lisent sans chercher.
5. **Servir le coup d'œil autant que la session longue.** L'état général se lit en quelques secondes ; le détail est à portée sans changer d'outil.

## Accessibility & Inclusion

WCAG 2.2 AA. Contraste vérifié dans les deux thèmes, navigation complète au clavier, focus visible, cibles tactiles d'au moins 44 px sur tablette, respect de `prefers-reduced-motion`. Vérifié en CI par Playwright et `axe`, sans violation sérieuse.
