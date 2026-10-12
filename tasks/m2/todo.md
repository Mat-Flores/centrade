# Tâches — Jalon M2

Plan : `tasks/m2/plan.md`. Une case n'est cochée qu'avec sa preuve (commande et résultat, nom de test, capture).

## Critères d'acceptation (§14)

- [x] Une instance Freqtrade en dry-run démarre, s'arrête et remonte ses trades. Preuve : `uv run pytest -q -s tests/freqtrade_adapter/test_ft_real.py`, trois passages verts de suite le 2026-10-12 (états observés : `exits_only` en paper, `running` après `resume_entries`, position remontée avec stop tenu par le moteur, `exits_only` après `pause_entries`, trade clos de cause `manual`, `stopped`, puis `exits_only` à la relance avec les trades clos conservés)
- [x] La valeur d'un secret n'est jamais renvoyée par l'API (test). Preuve : `test_i12_la_valeur_saisie_ne_ressort_nulle_part`, `test_i12_aucun_module_de_l_api_n_importe_le_dechiffrement` et `tests/scenarios/test_comptes_et_cles.py`
- [x] Revue de sécurité du SecretStore. Preuve : auditeur indépendant, verdict « acceptable à M2 » ; limites dans `docs/decisions/0009-ecarts-m2.md` (points 13 à 15) et `docs/security/threat-model.md` (X20)
- [x] Faits de l'annexe C revérifiés sur le tag épinglé (ADR). Preuve : `docs/decisions/0008-freqtrade-tag-et-annexe-c.md`, image `freqtradeorg/freqtrade:2026.9`
- [x] Capacité mesurée et consignée. Preuve : `docs/capacite.md`
- [x] `make lint` vert ; `uv run pytest -q` : 995 passés, 3 sautés ; vitest 145 ; Playwright 106 ; tests sur Docker local 9 ; détecteur de design sans constat ; gitleaks sans fuite
- [x] `docker compose up` fonctionnel. Preuve (2026-10-12) : `make up` puis `make engines-up`, code de sortie 0 ; six services sains et socket proxy en marche ; migrations de 0004 à 0009 sans perte (`users` 1 → 1, `instances` 2 → 2) ; `GET /api/v1/system/health` : base, bus et worker `ok` ; table `engines` : moteur réel enregistré avec son digest. Le premier essai a échoué à la construction (`.dockerignore` n'autorisait pas le paquet de l'adaptateur), corrigé. Reste à l'opérateur : `sudo install -d -m 700 -o 10001 /run/centrade` (Docker crée ce dossier au nom de root, le worker ne peut pas y écrire)
- [ ] CI verte : à confirmer par l'opérateur après autorisation de pousser

## Invariants

- [x] I2 — `tests/invariants/test_i02_une_seule_porte.py` : 3 tests verts ; réserve : le refus réel de l'entrée forcée ne repose que sur l'essai réel, local, hors CI
- [x] I3 — `tests/invariants/test_i03_mode_verifie.py` : 5 tests verts
- [x] I9 — `tests/invariants/test_i09_independance_plateforme.py` : 7 tests verts ; partiel pour « entrées refusées pendant la panne » (hook de risque, M3)
- [x] I10 — `tests/invariants/test_i10_empreinte.py` : 8 tests verts ; la promotion refusée à empreinte différente arrive à M7
- [x] I12 — `tests/invariants/test_i12_frontiere_dechiffrement.py` (7 tests) et `test_i12_secrets_sens_unique.py` (2 tests), verts

## Scénarios

- [x] S1 — déploiement en paper : `test_s01_deploiement_paper_de_bout_en_bout`
- [x] S5 — plateforme arrêtée puis relancée : `test_s05_plateforme_arretee_5_minutes_puis_relancee` ; partiel pour les entrées pendant la panne (M3)
- [x] S7 — écart de mode : `test_s07_ecart_de_mode_entrees_jamais_ouvertes`
- [x] S8 — dérive de configuration : `test_s08_derive_detectee_en_60_s_sorties_seules_alerte_critique` (horloge injectée)

## Lots

### Vague 1
- [x] A — socle de données, dépendances, empreinte : ADR 0007, migration 0005, `test_i10_*`
- [x] D1 — Freqtrade, partie pure, annexe C : ADR 0008, `test_i02_*`

### Vague 2
- [x] B — SecretStore, comptes et clés : `test_i12_*`, `tests/scenarios/test_comptes_et_cles.py`
- [x] C — registre de stratégies (contrôles statiques en refus par défaut, ADR 0008)
- [x] E — runner Docker, profil `engines` : `deploy/compose/engines.yml`, `test_i09_arret_du_worker_ne_touche_aucun_conteneur` (Docker local)

### Point de contrôle : `make lint test`

### Vague 3
- [x] D2 — FreqtradeAdapter, exécution : `tests/freqtrade_adapter/`, essai réel `test_ft_real.py`
- [x] F — worker : vérification de F9, dérive, adoption : `test_i03_*`, `test_i09_*`, `test_s05_*`, `test_s07_*`, `test_s08_*`
- [x] G — API instances et trading : `tests/scenarios/test_instances_trading.py`, `test_fermeture_et_annulation.py`

### Point de contrôle : `make lint test`

### Vague 4
- [x] H1 — navigation, Comptes et clés, Ordres et positions : captures `docs/captures/m2/comptes-*.png`, `ordres-*.png`
- [x] H2 — Stratégies : captures `docs/captures/m2/strategies-*.png`
- [ ] W — récepteur d'événements des moteurs : **non fait**, reporté à M3 (`docs/decisions/0009-ecarts-m2.md`, point 2)

### Lots ajoutés en cours de jalon
- [x] R — re-confirmation du TOTP (`POST /auth/totp/confirm`) : `apps/api/tests/auth/test_totp_confirm.py`
- [x] T — projection des trades clos et compléments d'API pour les écrans : `tests/scenarios/test_trades.py`, `test_api_complements.py`
- [x] Trois lots de correctifs issus des revues indépendantes

### Vague 5
- [x] I — assemblage, essai réel en dry-run, capacité, documentation : `test_ft_real.py`, `docs/capacite.md`, ADR 0009

## Clôture

- [x] Revues indépendantes (sécurité, code, interface) ; constats critiques et élevés corrigés : trois lots de correctifs ; dette non traitée dans `docs/decisions/0009-ecarts-m2.md` (points 16 à 18)
- [x] Contrôle des skills déclenchés : `insecure-defaults:audit` en repli manuel (`make insecure-sweep`), faute d'outil `Workflow`
- [x] `docs/invariants.md`, `docs/security/threat-model.md`, README (hypothèses), `docs/agentic/couts.md` : mis à jour le 2026-10-12 ; coût en dollars à compléter par l'opérateur
- [ ] `/graphify` puis `/clear` : à faire par l'opérateur
