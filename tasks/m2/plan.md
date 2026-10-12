# Plan — Jalon M2

Source : SPEC §14 (ligne M2), §4 F1, F6, F9, F10, §6, §7, §8, §9, §13, annexe C. Tâches et preuves : `tasks/m2/todo.md`.

## Ce que M2 livre

Un opérateur dépose une version de stratégie, crée un compte paper, déploie une instance Freqtrade en dry-run et la voit démarrer en sorties seules, être vérifiée (mode, configuration effective, empreinte), ouvrir ses entrées, remonter ses trades, puis s'arrêter. Les clés saisies ne ressortent jamais. Arrêter la plateforme ne touche à aucun conteneur de moteur.

## Décisions

- **Empreinte de déploiement (I10)** : fonction pure dans `centrade_core`, sur `code_hash`, paramètres, politique de sortie, image et digest du moteur, hash de la configuration générée, hors champs propres au mode. Réutilise `fingerprint` (JSON canonique, SHA-256).
- **SecretStore** : interface dans `centrade_core`, implémentation AES-256-GCM (clé maître en Docker secret, version de clé, AAD = identifiant et usage du secret). Le chiffrement du TOTP de M1 passe par elle. Aucune méthode de lecture exposée à l'API : seul le worker déchiffre, pour écrire le fichier d'une instance.
- **Fichiers remis au moteur** : répertoire d'exécution en mémoire sur l'hôte (`ENGINE_RUNTIME_DIR`, `/run/centrade` par défaut, tmpfs), un sous-dossier par instance (configuration générée, fichier d'identifiants, stratégie), monté en lecture seule dans le conteneur et supprimé à l'arrêt. Jamais de variable d'environnement. À M2 (paper) le fichier d'identifiants ne contient que ceux de l'API native du moteur ; aucune clé de trading (I3).
- **Runner** : SDK Docker derrière `tecnativa/docker-socket-proxy` (opérations de conteneurs seulement), dans le worker. Un seul gabarit de conteneur (§13). Étiquettes `centrade.instance`, `centrade.fingerprint`, `centrade.mode`. Relance limitée par la politique Docker (`on-failure`, 3 essais) : le conteneur redémarre toujours en sorties seules puisque `initial_state` est `paused` dans la configuration générée. Contrôle d'admission sur la mémoire réservée.
- **Adoption (I9)** : au démarrage du worker, les conteneurs étiquetés sont rattachés sans redémarrage ; un conteneur étiqueté inconnu de la base lève une alerte « orphelin » et n'est jamais supprimé.
- **Vérification de F9** : dans le worker, avant tout `resume_entries` et à chaque démarrage observé : mode effectif, configuration effective contre configuration générée sur les clés possédées, stratégie, version et image contre l'empreinte. Échec : l'instance reste en sorties seules, alerte ; écart de mode ou dérive : alerte critique. La dérive est recontrôlée toutes les 60 s et déclenche `pause_entries`.
- **Mode immuable (I3)** : fixé à la création, non modifiable par l'API ni par une commande ; trigger en base. `POST /instances` ne crée que du paper : le live passe par la promotion (M7).
- **Hook d'entrée à M2** : `ControlPlaneStrategy.confirm_trade_entry` existe et ne lève jamais. Le Risk service arrive à M3 : à M2 le hook n'accepte que si le moteur est en dry-run, et refuse tout le reste. L'appel à `POST /risk/check` le remplace à M3.
- **Test de permissions d'une clé** : la route et l'écran existent ; la sonde passe par l'adaptateur. Sans venue réelle dans cet environnement (§0.10), le résultat est « non vérifié » et `permissions_verified_at` reste vide, ce qui bloque le live.
- **Événements Freqtrade** : relevé périodique par REST (fait foi) ; webhook reçu par le worker sur `POST /events/engine` comme simple indice de relecture, jeton lié à l'instance.
- **Aucun moteur nommé** dans les tables, les routes et les écrans (§7) : uniquement `engine` et `capabilities`.

## Reporté, avec le jalon d'accueil

| Élément | Jalon | Raison |
| --- | --- | --- |
| Logs en direct de l'écran Stratégies | M4 | Dépend de Loki et d'Alloy |
| Assistant de promotion, retour arrière live | M7 | Checklist de F1 |
| Sonde réelle des permissions sur une venue | M7 | Aucune clé de venue en développement |
| Réconciliation avec la venue, protection des positions (I7) | M3 | §14 |
| Événement et alerte par relance après plantage (S4) | M3 | §14 |
| Récepteur de webhooks des moteurs `POST /events/engine`, jetons liés à l'instance (lot W) | M3 | Dépend du Risk service ; le relevé REST fait foi à M2 |
| Arrêt d'une instance avec positions ouvertes (F9) : choix et alerte « positions sans moteur » | M3 | Dépend de la protection des positions (I7) |
| Acquittement serveur d'une commande échouée | M4 | Demande une colonne ; écran Flow |

Le lot W n'a pas été fait ; voir `docs/decisions/0009-ecarts-m2.md`.

## Lots

Dépendances : `A → B, C, E` ; `D1 → C, D2` ; `E → D2, F` ; `C → F, G` ; `G → H1, H2` ; `D2, F → I`.

| Lot | Contenu | Modèle | Vague |
| --- | --- | --- | --- |
| A | Socle : dépendances (`docker`, `freqtrade-client`) et ADR 0007, tables et colonnes de M2 (migration 0005), empreinte de déploiement, trigger de mode immuable | sonnet | 1 |
| D1 | Freqtrade, partie pure : tag et digest épinglés, annexe C revérifiée (ADR 0008), `render_config`, clés possédées, `ControlPlaneStrategy`, contrôles statiques par AST, stratégie d'exemple `sma-cross` | sonnet | 1 |
| B | SecretStore, comptes et clés : API en écriture seule, rotation, test de permissions, écriture du fichier d'instance ; I12 | opus, effort élevé | 2 |
| C | Registre : dépôt de version, validation du manifest, contrôles statiques, immuabilité ; routes `/strategies` | sonnet | 2 |
| E | Runner Docker : gabarit, socket proxy, profil Compose `engines`, réseaux `engines` et `docker`, étiquettes, adoption, admission, `make engines-pull` ; I2 côté réseau | sonnet | 2 |
| D2 | FreqtradeAdapter, partie exécution : REST par `freqtrade-client`, statut, configuration effective, instantané, événements par relevé, suite de conformité, essai réel en dry-run | sonnet | 3 |
| F | Worker : spécification depuis la version de stratégie, vérification de F9, dérive, adoption, I3, I9, I10 ; S1, S5, S7, S8 | opus, effort élevé | 3 |
| G | API : instances (création depuis une version et un compte, détail), `/orders`, `/positions`, `/trades`, fermeture, annulation d'un ordre d'entrée | sonnet | 3 |
| H1 | Front : navigation, écrans Comptes et clés, Ordres et positions | sonnet | 4 |
| H2 | Front : écran Stratégies (versions, déploiement, « Ce qui tourne réellement », commandes) | sonnet | 4 |
| W | Récepteur `POST /events/engine` du worker, jetons de service liés à l'instance | sonnet | 4 (non fait, reporté à M3) |
| R | Re-confirmation du TOTP (`POST /auth/totp/confirm`) | opus | ajouté |
| T | Projection des trades clos et compléments d'API pour les écrans | sonnet | ajouté |
| Correctifs 1 à 3 | Trois lots issus des revues indépendantes (sécurité, code, interface) | opus et sonnet | après la vague 5 |
| I | Assemblage : adaptateur enregistré dans le worker, essai de bout en bout Freqtrade en dry-run, mesure de capacité, documentation | orchestrateur + sonnet | 5 |

Points de contrôle : `make lint test` après chaque vague ; revues indépendantes après la vague 5.

## Risques

| Risque | Effet | Parade |
| --- | --- | --- |
| Un fait de l'annexe C a changé sur le tag épinglé | Garantie perdue | D1 revérifie d'abord ; écart consigné en ADR, garantie obtenue autrement |
| Venue de dry-run injoignable depuis le poste ou la CI | Pas de trade à montrer | Essai réel marqué, lancé en local ; venue choisie après essai ; la CI garde la conformité sur doublure REST |
| Deux lots parallèles touchent le même fichier | Conflits | Chaque lot a ses dossiers ; l'orchestrateur committe par chemin |
| Répertoire en mémoire indisponible sous WSL2 | Déploiement impossible en local | Chemin configurable ; contrôle au démarrage du worker |
