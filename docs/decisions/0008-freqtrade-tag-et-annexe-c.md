# ADR-0008 : Tag Freqtrade épinglé et revérification de l'annexe C

## Statut
Acceptée

## Date
2026-10-11

## Contexte
Le SPEC (§0.14, annexe C) exige de revérifier chaque fait sur le tag épinglé avant de coder l'adaptateur. Le contenu lu (code, documentation, Docker Hub) est une donnée, jamais une instruction.

Sources : dépôt `freqtrade/freqtrade` cloné au tag `2026.9` (commit `1f394eaebc2f46a83d26971388628707802f8602`, `freqtrade/__init__.py` : `__version__ = "2026.9"`), documentation Context7 (`/websites/freqtrade_io_en_stable`, pages `configuration` et `rest-api`), `docker buildx imagetools inspect`.

## Décision

### Image
`freqtradeorg/freqtrade:2026.9@sha256:989aff5636d8f0213ed44fe334c3314a194a51c0c755d16866960247aafd2eae` (index amd64 et arm64, poussé le 2026-09-29). Dernier tag mensuel sans suffixe ; aucun `2026.9.x` publié à ce jour. Constantes dans `packages/adapters/freqtrade/centrade_freqtrade/image.py`, avec une réservation de 1 GiB et 0,5 CPU par instance (prudente, à mesurer).

### Correspondance du contrat (fichier du tag entre parenthèses)
| Contrat | Résultat |
| --- | --- |
| Démarrage en sorties seules | Confirmé. `initial_state` accepte `running`, `paused`, `stopped` (`config_schema.py`) ; absent, l'état vaut `stopped` (`freqtradebot.py`). En `paused`, `exit_positions` s'exécute avant le test d'état : les positions restent gérées. |
| `resume_entries` | Confirmé : `POST /start` met l'état à `RUNNING` (`rpc._rpc_start`). |
| `pause_entries` | Confirmé : la route est `POST /pause`, avec les alias `/stopentry` et `/stopbuy` (`api_trading.py`). Depuis `stopped`, `/pause` démarre le bot en pause. |
| `flatten` | Confirmé : `POST /forceexit`, charge `{tradeid, ordertype?, amount?, price?}`, `tradeid: "all"` ; `RPCException("trader is not running")` si l'état est `stopped`. |
| `close_position` | Confirmé : `POST /forceexit` avec l'identifiant ; `amount` permet une sortie partielle. |
| `cancel_entry_order` | **Écart.** `DELETE /trades/<id>/open-order` existe mais annule **tous** les ordres ouverts du trade, sorties et stop compris (`_rpc_cancel_open_order`). Garantie obtenue autrement : l'adaptateur d'exécution relit le trade (`GET /status`) et n'appelle la route que si chaque ordre ouvert est un ordre d'entrée ; sinon la commande échoue (annuler une sortie ou un stop augmente le risque, F9). |
| `stop` | Confirmé : `POST /stop` ne fait que passer à `STOPPED`, sans gérer les positions. L'enchaînement de F9 reste nécessaire. |
| Statut, battement | Confirmé : `GET /health` (`last_process`, `last_process_ts`, `bot_start`…) ; `GET /show_config` (`state`). |
| Instantané | Confirmé : `/status`, `/balance`, `/trades`, `/profit`, `/locks`, plus `/whitelist`. |
| Hygiène de backtest | Confirmé : `lookahead-analysis` et `recursive-analysis` existent (`commands/arguments.py`). |

### `GET /show_config`
Renvoyées : `version`, `strategy_version`, `api_version`, `dry_run`, `trading_mode`, `stake_currency`, `stake_amount`, `available_capital`, `max_open_trades`, `minimal_roi`, `stoploss`, `stoploss_on_exchange`, `trailing_stop` et ses variantes, `order_types`, `bot_name`, `exchange`, `strategy`, `force_entry_enable`, `position_adjustment_enable`, `state`, `runmode`, `unfilledtimeout`, `exit_pricing`, `entry_pricing`, `timeframe`.

**Écart : ne sont pas renvoyées** `initial_state`, `tradable_balance_ratio`, `cancel_open_orders_on_exit`, `db_url`, la liste blanche des paires, `api_server.*`, `webhook.*`, `telegram.*` (la route « n'expose pas la configuration complète », `rpc._rpc_show_config`). Garantie obtenue autrement :
- `initial_state` : l'état observé (`state`, donc `paused` puis `exits_only` côté facade) est vérifié par `status`, avant tout `resume_entries`.
- liste blanche : `GET /whitelist` ; l'adaptateur d'exécution l'ajoute à la réponse sous `pair_whitelist` avant d'appeler `drift`.
- `tradable_balance_ratio`, `cancel_open_orders_on_exit`, `db_url`, interfaces : couvertes par l'empreinte du fichier généré (I10), par le gabarit de conteneur (réseau des moteurs seul) et par les tests I2. `config.OBSERVABLE_KEYS` liste ce que `drift` compare ; un test fixe la liste des clés non observables.

Différences de forme gérées par `drift` : `stake_amount` en chaîne ; `available_capital` et `stoploss` en flottants ; `max_open_trades` vaut -1 pour l'infini ; `exchange` est le nom seul (clé `exchange.name`) ; `stoploss_on_exchange` dérive de `order_types` ; `order_types` peut contenir des clés par défaut en plus des nôtres (comparaison par sous-ensemble) ; `state` remplace `initial_state`. Les nombres sont comparés comme décimaux normalisés (`50`, `50.0` et `"50"` s'égalent).

### Les huit faits
1. **Confirmé.** `confirm_trade_entry` n'est appelé que si `mode == "initial"` (`freqtradebot.py`, `execute_entry`) ; `pos_adjust` et `replace` l'ignorent.
2. **Confirmé.** `strategy_safe_wrapper(..., default_retval=True)` renvoie `True` après toute exception (`strategy_wrapper.py`). Le hook attrape tout et retourne `False`.
3. **Confirmé.** `confirm_trade_exit` est appelé pour toute sortie sauf `LIQUIDATION`, et un `False` annule l'ordre (`freqtradebot.py`). Il n'est pas appelé pour une sortie partielle. La base de la plateforme le fige à `True`.
4. **Confirmé, avec précision.** `StrategyResolver._override_attribute_helper` : la configuration l'emporte sur l'attribut, y compris `stoploss`, `trailing_*`, `minimal_roi`, `order_types`, `stake_*`, `max_open_trades`, `position_adjustment_enable`. `order_types` est **remplacé en bloc** (pas de fusion) : la configuration générée écrit toutes ses entrées. `dry_run`, `force_entry_enable`, `initial_state` sont lus dans la configuration seule. Les fichiers `--config` successifs sont fusionnés en profondeur, le dernier gagnant (`deep_merge_dicts`) ; les variables `FREQTRADE__…` l'emportent sur les fichiers (`configuration.py`) : le gabarit de conteneur n'en pose aucune.
5. **Confirmé, avec précision.** `dry_run` vaut `true` par défaut. La base par défaut est `sqlite:///tradesv3.dryrun.sqlite` en dry-run et `tradesv3.sqlite` sinon (`constants.py`, `configuration._process_trading_options`) : fichiers distincts, pas en mémoire. `render_config` écrit `db_url` par mode.
6. **Confirmé, avec précision.** `stoploss_on_exchange: True` dans 10 classes d'exchange : binance, bingx, bitget, bybit, gate, htx, hyperliquid, kraken, kucoin, okx. L'échec de pose déclenche `emergency_exit`, au type `order_types.emergency_exit` (défaut `market`). **En dry-run le stop est toujours tenu par le moteur** (`interface.py` : `not stoploss_on_exchange or dry_run`) : le stop sur la venue n'est vérifiable qu'en live (M7).
7. **Confirmé.** Le webhook n'envoie aucun en-tête d'authentification (`rpc/webhook.py`) ; `allow_custom_messages` vaut `true` par défaut (schéma) : il est imposé à `false`.
8. **Confirmé.** `/forceenter` exige `force_entry_enable` (`rpc._force_entry_validations`). L'API exige `enabled`, `listen_ip_address` (IPv4), `listen_port` (≥ 1024), `username`, `password`, `jwt_secret_key` (≥ 32 caractères).

### Hooks
- **Écart.** Le moteur lève `OperationalException` au chargement si une stratégie redéfinit `adjust_order_price` **et** `adjust_entry_price` ou `adjust_exit_price` (`strategy_resolver.py`). `adjust_order_price` est appelé pour les ordres d'entrée et de sortie (`replace_order`, argument `is_entry`) et aiguille vers les deux autres. La base de la plateforme ne redéfinit donc que `adjust_order_price`, qui maintient l'ordre en place ; elle ferme le remplacement d'ordre sans casser le chargement. Le registre refuse en outre `adjust_exit_price` (liste de hooks portée à sept) pour donner une erreur claire.
- `adjust_trade_position` n'est appelé que si `position_adjustment_enable` (`freqtradebot.py`) ; fermé deux fois (configuration et base). `leverage` n'est appelé qu'en futures ; la base le fige à 1.
- Chargement : le moteur cherche le texte `class <Nom>(` dans chaque `.py` du dossier de stratégies et ajoute ce dossier à `sys.path` : `control_plane.py` est monté à côté de la stratégie, qui doit tenir en un seul fichier. Le nom de classe est le nom du fichier d'`entrypoint`.

### Format de configuration
- `render_config` renvoie les clés possédées (`OWNED_KEYS`, notation pointée) en chaînes canoniques ; le fichier JSON complet vient de `config_file(spec)`. Les symboles et les paires viennent de `spec.params["pairs"]` (fournis par la plateforme, ignorés par `validate`) ; la venue et la devise de cotation en sont déduites. `available_capital` = mise × nombre de positions.
- **Argent.** Côté plateforme : `Decimal`. Le moteur lit des nombres JSON en flottants (`stoploss`, `minimal_roi`, `available_capital`… ; `stake_amount` en chaîne n'est admis que pour `unlimited`). La conversion se fait à l'écriture du fichier, en refusant toute valeur dont le flottant ne redonne pas exactement le décimal (`ValueError`).
- `stoploss_on_exchange` suit `exits.stop_on_venue` ; `webhook.enabled` reste `false` jusqu'au lot du récepteur (l'URL secrète viendra du second fichier).
- Second fichier (écrit par le worker, fusionné en dernier) : `{"api_server": {"username", "password", "jwt_secret_key", "ws_token"}}` (+ `webhook.url` plus tard), valeurs propres à l'instance, jamais dans le premier.

### Contournements du contrôle d'entrée et limites des contrôles statiques
Faille corrigée : la liste de hooks seule laissait une stratégie redéfinir `_entry_allowed`, affecter `self.config["dry_run"]`, ou passer par `getattr`/`type`/`__dict__`.
- Statique : tout nom défini par la base (méthodes, attributs de classe, `self.x = …`, dérivés du source de `control_plane.py` par `checks.PROTECTED_NAMES`) ne peut être ni défini ni affecté ni supprimé ; toute écriture sur `….config` est refusée ; `getattr`, `setattr`, `delattr`, `type`, `vars`, `globals`, `locals`, `__dict__`, `__class__`, `__bases__`, `__base__`, `__mro__`, `__subclasses__` et les `__setattr__`, `__delattr__`, `__getattribute__` sont refusés. Un test compare cette liste à `control_plane.PROTECTED`.
- Exécution : `ControlPlaneStrategy.__init_subclass__` lève `TypeError` si une sous-classe redéfinit un nom protégé. Le chargeur de Freqtrade n'attrape que `AttributeError`, `ModuleNotFoundError`, `SyntaxError`, `ImportError` et `NameError` (`iresolver.py`) : l'erreur remonte et le moteur ne démarre pas (sens sûr). `IStrategy` n'a ni `__init_subclass__` ni métaclasse ; `INTERFACE_VERSION` n'est plus redéfini par la base pour rester libre ; `timeframe`, `stoploss`, `minimal_roi`, `populate_*` restent redéfinissables (testé). `_abc_impl` est exclu de la liste, sinon toute sous-classe serait refusée.
- Mode : lu une fois dans `__init__` (`_boot_dry_run`, défaut refus) ; le hook exige aussi que `config["dry_run"]` soit encore vrai. Une modification ultérieure de la configuration ne peut donc que refuser.
- Hors de portée d'un contrôle statique : du code Python arbitraire dans le même processus (alias de `self.config` puis écriture, accès par chaîne construite, objets obtenus par un module autorisé, `__init_subclass__` contourné par métaclasse indirecte, modification de la classe de base importée) reste possible. Les contrôles sont une défense en profondeur ; les garanties qui ne dépendent pas du code de la stratégie sont la configuration possédée (relue, F9), la détection d'entrée non autorisée (I6, M3) et l'isolation du conteneur.

## Essai réel du lot D2 (2026-10-11, image épinglée par digest, dry-run, venue `kraken`)
Instance de la stratégie de test (`tests/freqtrade_adapter/local_runtime.py`, un signal par bougie de 1 min) : démarrée en sorties seules, vérifiée sans dérive ni refus, `resume_entries` observé `running`, trade rempli remonté, `pause_entries` observé en sorties seules, `close_position` suivi d'un trade clos de cause `manual`, `stop` observé, identifiants supprimés, relance en sorties seules avec l'historique du volume conservé. Commande : voir `tests/freqtrade_adapter/test_ft_real.py`. Écarts et précisions :

- **Forme de la configuration acceptée.** Les deux fichiers `--config` fusionnent bien, le second en dernier. Le moteur plante au démarrage (`KeyError: 'exit_pricing'`) si `entry_pricing` et `exit_pricing` manquent : `render_config` les écrit (non possédés, hors empreinte de clés). Le bloc `telegram` doit être **omis** : le schéma exige `token` et `chat_id` dès que le bloc existe, même avec `enabled: false` (`telegram.enabled=false` reste dans `render_config`, il est non relisible). `--strategy` en ligne de commande l'emporte sur `strategy` du fichier ; l'adaptateur passe le même nom aux deux.
- **`entry_pricing.price_side`.** Avec `same` (défaut du moteur), l'ordre limite d'entrée reste posé sur le carnet et ne se remplit pas en dry-run (observé : aucune exécution en 4 min) ; une sortie limite resterait de même en attente, ce qui retarde une sortie (I4). La plateforme écrit `other` (l'ordre traverse le carnet) pour l'entrée et la sortie. Choix d'exécution, pas de stratégie.
- **Utilisateur et racine en lecture seule.** L'image tourne par défaut sous `ftuser` (1000:1000). Elle tourne ici sous `container_user()` (uid:gid du worker), racine en lecture seule, toutes capacités retirées : confirmé. **Écart : un volume neuf appartient à root** et le moteur n'y crée rien (`PermissionError` sur `/data/backtest_results`). Garantie obtenue autrement : le runner crée, avant le premier démarrage, le sous-dossier `/data/engine` au nom de l'utilisateur du conteneur (`put_archive` sur `/data` ; sur `/` l'API refuse, racine en lecture seule) ; le moteur reçoit `--userdir /data/engine` et `db_url` dans ce dossier. Passe par le socket proxy (`POST=1` couvre le `PUT`). Aucun durcissement retiré. Alternative écartée : un conteneur d'initialisation sous root avec `CAP_CHOWN`.
- **Lecture du statut.** `GET /show_config` : `max_open_trades` en flottant (`3.0`), `stake_amount` en chaîne (`"50.0"`), `stoploss_on_exchange` vrai en dry-run (dérivé de `order_types`, sans effet : le stop est tenu par le moteur), `state` vaut `running`, `paused` ou `stopped`. `GET /health` donne `last_process_ts` (secondes). Une `RPCException` du moteur sort en HTTP 502 avec `detail` : l'adaptateur la lit comme un refus (`CommandRejected`), tout autre 5xx, 401 ou 403 comme un moteur injoignable.
- **Trades.** Un trade existe dès l'ordre d'entrée posé : `amount` 0, `nr_of_successful_entries` 0, `stop_loss_abs` déjà renseigné. La position n'existe qu'à partir d'un remplissage (`nr_of_successful_entries` > 0). `enter_tag` vaut `""` : l'adaptateur écrit la cause d'entrée `signal` (`force_entry_enable` est faux, il n'y a pas d'autre origine). `GET /trades` ne rend que les trades clos ; la fenêtre relue à chaque tour est de 50 (les plus récents par date de clôture) ; le worker écrit `ON CONFLICT DO NOTHING` sur l'identifiant du trade, qui est aussi celui de la position ouverte.
- **Annulation.** `DELETE /trades/<id>/open-order` répond 502 (« No open order » ou « no active trade ») quand l'ordre s'est rempli ou annulé entre la lecture et l'appel : l'adaptateur le lit comme fait (effet voulu atteint). `POST /forceexit` peut dépasser 5 s : délai de 20 s pour cette seule route.
- **Freqtrade-client.** Les routes sont celles de `freqtrade-client` 2026.9, mais le client n'est pas utilisé : il lit les nombres en `float` (règle 5), ignore le code HTTP et avale les erreurs de connexion. L'adaptateur appelle les routes avec `requests` et décode les nombres en `Decimal` (`parse_float`).

### Clés possédées non relisibles (`EngineConfig.unreadable`)
`db_url`, `initial_state`, `tradable_balance_ratio`, `cancel_open_orders_on_exit`, `api_server.enabled`, `api_server.listen_ip_address`, `api_server.listen_port`, `webhook.enabled`, `webhook.allow_custom_messages`, `telegram.enabled` : `GET /show_config` ne les rend pas (voir plus haut). Garanties : `initial_state` par l'état `exits_only` observé avant toute reprise ; `db_url` par le gabarit (volume de l'instance seul) ; `api_server.*` par le réseau `engines` et la réponse de l'API elle-même ; `webhook.*` et `telegram.*` par l'empreinte du fichier et le test de rendu ; `tradable_balance_ratio` et `cancel_open_orders_on_exit` par l'empreinte. `exchange.pair_whitelist` se relit par `GET /whitelist`. Clés propres à l'instance (hors hash I10) : `dry_run`, `db_url`, `bot_name`.

### Raisons de sortie (`ExitType`, tag 2026.9) vers F10
`roi` -> `take_profit` ; `stop_loss`, `stoploss_on_exchange` -> `stop_loss` ; `trailing_stop_loss` -> `trailing_stop` ; `exit_signal`, `custom_exit` -> `signal` ; `force_exit` -> `manual` ; `emergency_exit` -> `engine_protection` ; `liquidation` -> `liquidation` ; toute autre valeur (dont `partial_exit`, `sold_on_exchange`, vide) -> `unknown`. `force_exit` ne distingue pas un `manual`, un `flatten` ni le kill switch côté moteur : la plateforme, qui sait quelle commande elle a envoyée, affine. `position.closed` n'a pas de cause hors de l'énumération : `unknown` a été ajouté à `ExitCause` (`centrade_core/events.py`).

### Événements
Relevé par comparaison de deux lectures de l'API (le relevé fait foi) ; identifiants déterministes (UUID v5 de l'instance et de l'objet), donc un rejeu ou un worker redémarré ne crée aucun doublon. La séquence repart d'un compteur par processus, amorcé sur l'heure en secondes pour passer devant celle d'un processus précédent (un trou unique, lu comme écart par l'ingestion, déclenche une relecture). Limite connue : plus de 50 trades clos entre deux tours échappent au relevé ; l'intervalle du worker est de quelques secondes.

## Alternatives écartées
- Épingler `stable` ou `develop` : non reproductible (§0.14).
- Traiter l'absence d'une clé dans `show_config` comme une dérive : l'instance ne passerait jamais la vérification de F9 pour des clés que le moteur ne montre pas.
- Utiliser `freqtrade-client` tel quel : flottants, erreurs avalées, `forceenter` à portée de main.
- Redéfinir aussi `adjust_entry_price` dans la base : le moteur refuserait de charger toute stratégie.

## Conséquences
- L'adaptateur d'exécution (D2) doit : n'annuler un ordre que s'il est une entrée ; ajouter `pair_whitelist` avant `drift` ; passer le second fichier au conteneur.
- Le stop sur la venue ne se teste pas avant le live.
- Un changement de tag impose de rejouer cette vérification.
