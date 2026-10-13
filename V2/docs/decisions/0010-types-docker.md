# ADR-0010 : `types-docker`, types de la bibliothèque Docker

## Statut
Acceptée (opérateur, 2026-10-13)

## Date
2026-10-13

## Contexte
À la racine du dépôt V1, le dossier `docker/omniroute/` porte le même nom que la bibliothèque `docker`. `ruff` et `mypy` la prenaient pour du code local : les appels du runner à Docker n'étaient pas vérifiés, et des commentaires `type: ignore` masquaient l'absence de types. La copie du backend dans `V2/`, sans ce dossier, a révélé le défaut.

## Décision

| Paquet | Version | Rôle | Portée |
| --- | --- | --- | --- |
| `types-docker` | 7.2.0.20261006 | types (typeshed) du SDK Docker, lus par `mypy` | développement seulement, jamais dans une image |

Les `type: ignore` devenus inutiles sont retirés. Le code du runner (`centrade_worker/runner.py`) passe la vérification sans autre changement. Trois écarts, tous dans des aides de test, sont traités sur place : un port hôte `None` que les types ne décrivent pas, un nom de réseau possiblement absent, une doublure de réponse HTTP.

## Audit de la dépendance
Audit `supply-chain-risk-auditor` du 2026-10-13, sur ce seul paquet : aucun avis de sécurité connu, paquet non déprécié, dépôt actif et non archivé, aucun signal sur les contrôles OpenSSF Scorecard évalués. Non évaluables sur PyPI : concentration des éditeurs, scripts d'installation, provenance de publication, volume de téléchargement.

## Conséquences
- Le lint de `V2/` ne dépend plus de la présence d'un dossier nommé `docker`.
- Toute évolution du SDK Docker demande de mettre à jour les types en même temps.
