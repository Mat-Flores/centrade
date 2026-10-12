# ADR-0009 : Écarts et reports acceptés à M2

## Statut
Acceptée, sauf le premier point (client officiel), qui reste à valider par l'opérateur.

## Date
2026-10-12

## Contexte
Des choix faits à M2 s'écartent du SPEC, en restreignent la lettre ou reportent une exigence à un jalon ultérieur. Chaque point a été relu dans le code ou dans les ADR à la clôture du jalon (§0.14). Pour chacun : ce que dit le SPEC, ce qui est fait, pourquoi, quand c'est levé.

## Décision

### Écarts au SPEC
1. **`freqtrade-client` non utilisé (à valider par l'opérateur).** SPEC : §5 et §7 imposent le client officiel. Fait : l'adaptateur appelle les mêmes routes avec `requests` et décode en `Decimal`. Pourquoi : le client rend des flottants et ignore les codes HTTP. Détail et voie de retour : ADR 0007. Levé : à la décision de l'opérateur.
2. **Récepteur de webhooks des moteurs `POST /events/engine` reporté à M3.** SPEC : événements des moteurs reçus sans délai, interface à jour en moins d'une seconde (§13). Fait : le relevé périodique par REST fait foi (`event_transport="poll"`) et `webhook.enabled` reste à `false` dans la configuration générée. Conséquence : pour un moteur réel, l'interface se met à jour au rythme du relevé, pas en moins d'une seconde. Levé : à M3, avec le Risk service et les jetons liés à l'instance. Le lot W du plan n'a pas été fait.
3. **Hook d'entrée limité au dry-run.** SPEC : le hook appelle `POST /risk/check` (§10). Fait : `ControlPlaneStrategy.confirm_trade_entry` accepte seulement si le moteur est en dry-run, refuse tout le reste et tout cas d'erreur. Levé : à M3, l'appel au Risk service le remplace.
4. **Sonde de permissions d'une clé non vérifiable.** SPEC : F6, test de connexion (trading autorisé, retrait interdit). Fait : la route et l'écran existent ; sans venue réelle en développement (§0.10) le résultat est « non vérifié » et `permissions_verified_at` reste vide, ce qui bloque le live. Levé : sonde réelle à M7.
5. **F9, arrêt d'une instance avec des positions ouvertes.** SPEC : l'opérateur choisit « fermer puis arrêter » ou « arrêter en laissant ouvert », avec l'alerte « positions sans moteur ». Fait : ni le choix ni l'alerte. Pourquoi : ils dépendent de la protection des positions (I7). Levé : à M3.
6. **Acquittement d'une commande échouée.** Fait : « marquer comme vu » reste local au navigateur (ADR 0006, point 5). L'acquittement côté serveur demande une colonne. Levé : à M4 (écran Flow, file des commandes).
7. **Écrans.** Stratégies : logs en direct à M4, assistant de promotion et retour arrière à M7. Comptes et clés : la matrice instance et compte reste à faire, le solde comparé au plafond affiche « non disponible » (M3 : réconciliation).

### Comportements retenus
8. **État `halted` observé** : alerte et `pause_entries` ; pas de relance automatique, puisque le doute refuse `start` (I5).
9. **Plantage d'un moteur.** La relance est limitée par la politique Docker (`on-failure`, 3 essais, `apps/worker/centrade_worker/runner.py`) et se fait toujours en sorties seules. L'événement et l'alerte par relance (S4) viennent à M3.
10. **Durée d'une tâche d'instance.** Le worker traite chaque instance dans sa propre tâche. Sa durée est bornée par la somme des délais d'appel (environ deux minutes au pire) : la pause d'un moteur lent attend d'autant, sans retarder les autres instances (`tests/test_worker_parallele.py`).
11. **Venue de l'essai réel : `kraken`.** Valeur d'exemple choisie parce qu'elle est joignable depuis le poste ; ce n'est pas une recommandation.
12. **Contrôles statiques des stratégies.** La liste blanche d'imports est stricte : `qtpylib`, `technical` et `Trade` n'y figurent pas. Ce que l'analyse statique n'empêche pas est dans l'ADR 0008. Ce qui tient réellement, ce sont les garanties indépendantes de la stratégie : configuration générée et relue, conteneur durci, réseau `engines` interne.

### Risques résiduels
13. **Frontière de déchiffrement (I12) tenue par le code, pas par la cryptographie.** L'API détient la clé maître pour chiffrer à la saisie ; seuls le code et des tests d'import (`tests/invariants/test_i12_frontiere_dechiffrement.py`) empêchent qu'elle déchiffre. Acceptable tant qu'aucune clé de venue n'est remise. Avant le live : chiffrement à clé publique (clé privée chez le worker seul) et rotation de la clé maître. Aujourd'hui `key_version` n'entre pas dans les données associées (`secret_aad` : identifiant, propriétaire, usage), donc la rotation est impossible sans migration.
14. **Socket proxy.** Il filtre la méthode et le chemin, pas le corps de la requête : un worker compromis pourrait créer un conteneur privilégié. Risque résiduel, à durcir à M7 (plugin d'autorisation Docker ou démon sans privilèges dédié).
15. **`cancel_entry_order`.** Course entre la lecture des ordres et le `DELETE` de la route du moteur. Sans effet en dry-run ; à lever avant le live (M7).

### Dette relevée par la revue de code, non traitée
16. `ContainerSpec` est importé du worker par le paquet de l'adaptateur (`centrade_freqtrade/adapter.py`) : sens de dépendance inversé.
17. Deux registres de moteurs : celui de l'API (contrôles statiques) et celui du worker (exécution).
18. `Idempotency-Key` est facultatif sur `POST /instances` (clé par défaut `deploy:<id>`), obligatoire sur les commandes.

## Alternatives écartées
- Corriger les points 2, 5 et 14 dans M2 : ils dépendent du Risk service et de la protection des positions (M3) ou du durcissement final (M7), et les faire à moitié aurait créé un faux sentiment de garantie.
- Cacher le point 2 en annonçant « temps réel » : l'interface affiche l'âge de chaque valeur (I1), la lenteur est visible.

## Conséquences
- Les risques 13 et 14 sont inscrits dans `docs/security/accepted-risks.md` avec une expiration avant toute promotion en live (M7), proposés à l'opérateur pour décision.
- Aucun de ces points n'est un obstacle à l'usage en paper et en dry-run, seul périmètre de M2.
