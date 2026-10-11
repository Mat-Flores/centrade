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
| `freqtrade-client` | 2026.9 | client REST officiel de Freqtrade, utilisé par l'adaptateur | non : le §5 impose le client officiel |

Aucune autre dépendance. `freqtrade-client` apporte `python-rapidjson` 1.25 (et `requests`, déjà présent). `docker` était déjà dans le verrou comme dépendance de `testcontainers`.

## Audit de chaîne d'approvisionnement
Collecteur `supply-chain-risk-auditor` lancé le 2026-10-11 sur `pyproject.toml` et `uv.lock` : 22 dépendances directes, 45 transitives vérifiées.
- Aucun avis de sécurité connu pour `docker`, `freqtrade-client` ni leur arbre, aux versions verrouillées.
- Seul constat : Scorecard OpenSSF de `freqtrade-client`, Binary-Artifacts 8/10.
- Non évaluable (PyPI ne le publie pas) : concentration des éditeurs, scripts d'installation, provenance, téléchargements. Absence de constat n'est donc pas une garantie sur ces points.
À refaire à chaque montée de version.

## Alternatives écartées
- Appeler l'API REST de Freqtrade avec `httpx` : réécrit un client officiel et ses cas limites d'authentification.
- Piloter `docker` par sous-processus (`docker run`) : sortie à analyser, pas de typage, pas de passage par le socket proxy.

## Conséquences
- `freqtrade-client` n'est utilisé que dans `packages/adapters/freqtrade/` ; `docker` que dans le runner du worker. Le cœur ne les importe pas.
- La version du client suit le tag Freqtrade épinglé (ADR 0008) : les monter ensemble.
