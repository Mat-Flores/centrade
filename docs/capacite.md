# Capacité d'un hôte : mesure des moteurs Freqtrade (M2)

Mesurée le 2026-10-11 avec `scripts/measure-capacity.py` (statistiques Docker lues sur l'hôte, hors socket proxy), image `freqtradeorg/freqtrade:2026.9` épinglée par digest, gabarit de conteneur du runner, dry-run sur la venue d'exemple `kraken` (données publiques, valeur d'exemple, pas une recommandation).

## Poste de mesure
WSL2 (Linux 6.18), 20 CPU logiques, 7,7 Gio de mémoire, Docker 29.9. Le poste n'est pas l'hôte de référence : le CPU y est surdimensionné, la mémoire est comparable.

## Résultats par instance
Stratégie de test (un signal à chaque bougie de 1 min), 2 paires, entrées ouvertes, trades réels simulés.

| Essai | Instances | Stabilisation | Mémoire (Mio, moy. / max) | CPU (% d'un cœur, moy. / max) |
| --- | --- | --- | --- | --- |
| 1 | 3 | 90 s | 275,3 à 275,6 / 276,0 | 0,4 à 1,3 / 4,5 |
| 2 | 5 | 20 s | 274,8 à 275,0 / 275,6 | 0,5 à 1,5 / 4,1 |

La mémoire est la même à 3 et à 5 instances (aucun partage mesurable). Le CPU est quasi nul entre les bougies ; le maximum correspond au traitement d'une bougie.

## Constantes retenues (`centrade_freqtrade/image.py`)
- Mémoire : 1 Gio devient **768 Mio** (2,8 fois la mesure). Un dépassement tue le moteur : la marge couvre plus de paires et un historique plus long. Ne pas descendre sans nouvelle mesure avec la vraie stratégie.
- CPU : **0,5** conservé (plafond de limitation, pas une moyenne ; le démarrage et le calcul d'une bougie y tiennent).
- Ces valeurs vont dans la ligne `engines` (réservation, contrôle d'admission du runner) et dans la limite du conteneur. À ce jour elles ne figurent pas dans la formule de l'empreinte de déploiement (`guard.spec_for` : code, paramètres, sorties, image, digest, configuration) : leur changement ne déclenche pas d'écart d'empreinte, mais n'affecte que les conteneurs créés après.

## Extrapolation prudente pour l'hôte de référence (4 vCPU, 8 Go, SPEC §15)
Hypothèse : 3 Go réservés au système, à Postgres/Timescale, Redis, API, worker, web et observabilité ; 5 Go pour les moteurs.
- Par la réservation : 5 Gio / 768 Mio = **6 instances admises** (6 x 0,5 = 3 vCPU réservés sur 4).
- Par la consommation mesurée : environ 276 Mio chacune, soit une quinzaine d'instances en pratique ; non retenu comme capacité annoncée (stratégies plus lourdes, pics).
- Capacité annoncée : **6 instances en dry-run**. Au-delà, mesurer avec la stratégie réelle et réviser la réservation.
- Non mesuré ici : le live (flux de la venue, stop sur la venue), le démarrage simultané de nombreuses instances, une stratégie à indicateurs lourds.

## Relancer
`uv run python scripts/measure-capacity.py --count 3 --venue kraken` (Docker et l'image épinglée présents : `make engines-pull`).
