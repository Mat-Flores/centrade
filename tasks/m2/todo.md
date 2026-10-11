# Tâches — Jalon M2

Plan : `tasks/m2/plan.md`. Une case n'est cochée qu'avec sa preuve (commande et résultat, nom de test, capture).

## Critères d'acceptation (§14)

- [ ] Une instance Freqtrade en dry-run démarre, s'arrête et remonte ses trades
- [ ] La valeur d'un secret n'est jamais renvoyée par l'API (test)
- [ ] Revue de sécurité du SecretStore
- [ ] Faits de l'annexe C revérifiés sur le tag épinglé (ADR)
- [ ] Capacité mesurée et consignée
- [ ] `make lint test` vert ; `docker compose up` fonctionnel
- [ ] CI verte (à confirmer par l'opérateur après autorisation de pousser)

## Invariants

- [ ] I2 — `tests/invariants/test_i02_une_seule_porte.py`
- [ ] I3 — `tests/invariants/test_i03_mode_verifie.py`
- [ ] I9 — `tests/invariants/test_i09_independance_plateforme.py`
- [ ] I10 — `tests/invariants/test_i10_empreinte.py`
- [ ] I12 — `tests/invariants/test_i12_*` (complété pour le SecretStore et l'API)

## Scénarios

- [ ] S1 — déploiement en paper
- [ ] S5 — plateforme arrêtée puis relancée
- [ ] S7 — écart de mode
- [ ] S8 — dérive de configuration

## Lots

### Vague 1
- [ ] A — socle de données, dépendances, empreinte
- [ ] D1 — Freqtrade, partie pure, annexe C

### Vague 2
- [ ] B — SecretStore, comptes et clés
- [ ] C — registre de stratégies
- [ ] E — runner Docker, profil `engines`

### Point de contrôle : `make lint test`

### Vague 3
- [ ] D2 — FreqtradeAdapter, exécution
- [ ] F — worker : vérification de F9, dérive, adoption
- [ ] G — API instances et trading

### Point de contrôle : `make lint test`

### Vague 4
- [ ] H1 — navigation, Comptes et clés, Ordres et positions
- [ ] H2 — Stratégies
- [ ] W — récepteur d'événements des moteurs

### Vague 5
- [ ] I — assemblage, essai réel en dry-run, capacité, documentation

## Clôture

- [ ] Revues indépendantes (sécurité, code, interface) ; constats critiques et élevés corrigés
- [ ] Contrôle des skills déclenchés
- [ ] `docs/invariants.md`, `docs/security/threat-model.md`, README (hypothèses), `docs/agentic/couts.md`
- [ ] `/graphify` puis `/clear` par l'opérateur
