# ADR-0007 : Dépendances du jalon M2

## Statut
Acceptée

## Date
2026-10-11

## Contexte
M2 déploie une instance Freqtrade en dry-run (SPEC §14). Le worker doit créer, adopter et arrêter des conteneurs, et piloter l'API REST du moteur. Les versions exactes sont figées par `uv.lock`.

## Décision

| Paquet | Version | Rôle | Hors §5 ? |
| --- | --- | --- | --- |
| `docker` | 7.2.0 | SDK Python Docker du runner (derrière le socket proxy, opérations de conteneurs seulement) | non : le §5 impose le SDK Docker |
| `requests` | 2.34.2 | appels REST de l'adaptateur Freqtrade (`centrade_freqtrade/client.py`) | **oui : voir l'écart ci-dessous** |

Aucune autre dépendance. `requests` était déjà dans le verrou (dépendance de `docker`) : il est désormais déclaré, puisque l'adaptateur l'importe directement. `docker` était déjà dans le verrou comme dépendance de `testcontainers`.

## Écart au SPEC, à faire valider par l'opérateur

Le SPEC §5 et §7 imposent le client officiel `freqtrade-client`. **Il n'est pas utilisé**, et il a été retiré des dépendances le 2026-10-12 (il était déclaré sans être importé, avec `python-rapidjson` 1.25 dans son sillage). Tant que l'opérateur n'a pas validé cet écart, il reste un écart, pas une décision acquise.

Motif, relevé dans `freqtrade_client/ft_rest_client.py` au tag 2026.9 :
- il décode les réponses en `float` : contraire à la règle « jamais de float pour l'argent » (CLAUDE.md, règle 5). L'adaptateur décode avec `parse_float=Decimal` ;
- il ne regarde pas le code HTTP et avale les erreurs de connexion (il journalise et rend `None`) : contraire à l'exigence « moteur injoignable ⇒ `unknown` » (I1, I5), qui demande de distinguer un refus du moteur, une panne et une réponse illisible ;
- il borne la durée d'un appel, pas la taille de la réponse lue.

Routes appelées, identiques à celles du client (mêmes chemins sous `/api/v1/`, mêmes paramètres, authentification HTTP Basic) : `GET /show_config`, `GET /health`, `GET /whitelist`, `GET /status`, `GET /balance`, `GET /trades` (`limit`, `offset`, `order_by_id`), `POST /start`, `POST /pause`, `POST /forceexit` (`tradeid`), `DELETE /trades/<id>/open-order`. `POST /forceenter` et `POST /stop` ne sont jamais appelées (I2, I11, F9) ; un test le vérifie.

Pour revenir au client officiel, il faudrait qu'il expose le texte brut et le code HTTP de la réponse. Si l'opérateur refuse l'écart, l'autre voie est d'envelopper le client (sous-classe qui redéfinit `_call`), ce qui garde la dépendance sans rien garder de son comportement.

## Audit de chaîne d'approvisionnement
Collecteur `supply-chain-risk-auditor` relancé le 2026-10-12 sur `pyproject.toml` et `uv.lock`, après le retrait de `freqtrade-client` et la déclaration de `requests` : 22 dépendances directes, 43 transitives vérifiées.
- Aucun avis de sécurité connu pour les 22 dépendances directes (dont `docker` 7.2.0 et `requests` 2.34.2) ni pour les 43 transitives, aux versions verrouillées.
- Aucune dépendance dépréciée, retirée, archivée ou sans activité de maintenance (22/22 évaluées).
- Non évaluable (PyPI ne le publie pas) : concentration des éditeurs, scripts d'installation, provenance, téléchargements (0/22). Scorecard OpenSSF absent pour 6 dépendances. L'absence de constat n'est donc pas une garantie sur ces points.
- Le changement retire deux paquets du verrou (`freqtrade-client`, `python-rapidjson`, ce dernier avec du code natif) et n'en ajoute aucun.
À refaire à chaque montée de version.

## Alternatives écartées
- Utiliser `freqtrade-client` tel quel : flottants, erreurs avalées (voir l'écart).
- Appeler l'API avec `httpx` : une dépendance directe de plus pour le même travail ; `requests` est déjà dans l'arbre.
- Piloter `docker` par sous-processus (`docker run`) : sortie à analyser, pas de typage, pas de passage par le socket proxy.

## Conséquences
- `requests` n'est importé que dans `packages/adapters/freqtrade/` ; `docker` que dans le runner du worker. Le cœur ne les importe pas.
- Les routes suivent le tag Freqtrade épinglé (ADR 0008) : à revérifier à chaque changement de tag, le client officiel servant de référence de lecture.
