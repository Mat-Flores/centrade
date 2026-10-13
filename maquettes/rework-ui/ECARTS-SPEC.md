# Écarts entre la maquette et `SPEC.md`

Décisions prises par l'opérateur le 12 octobre 2026, pendant le cadrage de la maquette. Rien n'est modifié dans `SPEC.md` : ce fichier liste ce qu'il faudra y changer si la maquette est validée.

## Décisions conformes au SPEC

| Sujet | Décision | Référence |
| --- | --- | --- |
| Passage en réel | Le mode réel ne se choisit pas à la création. Une instance en mode test porte « Passer en réel » : liste de contrôles, code TOTP, puis une copie réelle est créée. | F1, I3 |
| Modification à l'arrêt | Chaque modification crée une version n+1, visible dans un historique. En test et en backtest elle redémarre aussitôt ; en réel elle repasse par le mode test. | F1.4, I10 |
| Démarrage | Trois étapes visibles (Lancement, Vérification, Actif), chacune cochée seulement quand elle est observée. | F9, I8 |
| Comptes | Un seul compte par instance. | §2 |
| Devise | Montants dans la devise du compte, jamais convertis. | §9 |
| Backtest | Une période et un jeu de coûts par instance ; mention « un backtest n'est pas une prévision ». | F8 |

## Écarts à arbitrer dans le SPEC

| N° | Sujet | Ce que dit le SPEC | Décision pour la maquette | Modification du SPEC que cela implique |
| --- | --- | --- | --- | --- |
| E1 | Contenu d'une instance | Une instance = une version de stratégie, un compte, un mode, un conteneur (§2). | Une instance = un environnement : un compte, des paires, une stratégie affectée à chaque paire ; plusieurs paires peuvent partager une stratégie. | §2 et §6 : l'instance devient un groupe de bots (un par stratégie). À préciser : empreinte (I10) par bot ou par instance, commandes (F9) adressées au groupe, kill switch de niveau instance appliqué à tous ses bots, limites de risque au niveau du groupe. |
| E2 | Navigation | Dix écrans (§9). | Deux entrées principales, Instances et Bibliothèque ; Journal et Paramètres à part ; Flow et Agents dans « Avancé ». Ordres, Risque et Backtests sont absorbés par la vue d'une instance. | §9 « Écrans » à réécrire. Le Cockpit devient la liste des instances ; vérifier que le panneau « Garanties » et les positions non protégées gardent une place visible. |
| E3 | Couleur | Une seule couleur d'accent ; rouge réservé au mode réel et au danger (§9). | Code couleur complet : vert gain, rouge perte, bleu achats, ventes et valeurs en cours, une couleur par mode. Couleurs personnalisables (préréglages et réglage libre, avec avertissement de lisibilité). | §9 « Sobriété » : remplacer la règle de l'accent unique par un tableau des rôles de couleur. Garder l'exigence que le mode réel ne se confonde avec rien, même après personnalisation. |
| E4 | Mouvement | Transitions de 150 ms au plus, sans rebond (§9). | Expressif mais utile, jusqu'à 400 ms environ ; chaque animation montre un changement réel. | §9 « Mouvement » : relever le plafond et lister les animations admises. |
| E5 | Vocabulaire | Glossaire du §2 employé tel quel (`PRODUCT.md`). | Mots courants, terme technique en infobulle ; les mots déjà courants ne sont pas traduits (bot, trade, backtest, stop-loss). | §2 : ajouter une colonne « libellé d'interface ». Voir `VOCABULAIRE.md`. |
| E6 | Pile frontend | React 18, Vite, Tailwind, shadcn/ui, TanStack Query (§5). | La maquette ajoute Motion et GSAP pour les animations. | Si le portage les garde : ADR dans `docs/decisions/` et audit des dépendances. |
| E7 | Automatisations | Workflows n8n, limites de risque et agents sont trois sujets séparés (§10, §11, §12). | Regroupés sous « Automatisations » dans la Bibliothèque : alertes, règles de protection, planification, agents IA. | §9 : nouvel écran. À préciser : une règle de protection ne peut que réduire le risque (I4, I5) ; la planification d'un démarrage repasse par la vérification de F9 ; un agent propose, il n'agit pas (F5). |
| E8 | Solde | PnL jour et semaine, signe explicite (§9). | « 2 000,00 USDT ▲ +10,00 % » : résultat encaissé en vert ou rouge, variation en cours en bleu ; détail au clic. | §9 : décrire les deux variations et leur définition (réalisé net de frais ; latent sur positions ouvertes). |
| E9 | Indicateurs | Liste fixe par écran (§9). | Indicateurs activables un par un, les importants actifs par défaut. | §9 : liste des indicateurs, définition de chacun, lesquels sont actifs par défaut. |

| E10 | Provider | Aucun écran ne mentionne un moteur précis : uniquement `engine` et `capabilities` (§7). | Le provider (Freqtrade) est nommé à l'écran : étiquette de l'instance, filtre des stratégies, choix à la création. La fenêtre de création d'une stratégie est propre à chaque provider. | §7 et §9 : admettre le nom du moteur à l'écran, lu dans les données, et un formulaire de stratégie par adaptateur. La compatibilité stratégie-instance par moteur est déjà dans le SPEC (§4 F7 : comparaisons à l'intérieur d'un même moteur). |
| E11 | Vocabulaire (révise E5) | Glossaire du §2. | Termes techniques en anglais à l'écran, expliqués en français au survol. | §2 : colonne « libellé d'interface » en anglais pour les termes techniques. Voir `VOCABULAIRE.md`. |
| E12 | Accent en thème clair | Une seule couleur d'accent (§9). | En thème clair, l'accent est l'encre (boutons principaux, sélection) ; l'orange ne sert plus qu'aux avertissements et au mode test. Le thème sombre garde l'ambre. | §9 : préciser l'accent par thème. |

## Points que la maquette ne tranche pas

- Comment le moteur fait tourner plusieurs stratégies dans une instance (E1) : à vérifier sur le tag Freqtrade épinglé avant tout portage (annexe C).
- La lecture animée d'un backtest est une mise en scène du résultat stocké, pas une seconde exécution.
- La personnalisation des couleurs n'est pas enregistrée dans la maquette (aucune persistance).
