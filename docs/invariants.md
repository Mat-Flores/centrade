# Registre des invariants et des scénarios de référence

Source : SPEC §1.2 (invariants), §14 (jalons, scénarios), §0.13. À M0, **rien n'est testé** : ce document est un plan. L'état d'une ligne passe de `prévu` à `testé` quand le test existe et passe. `tests/invariants/test_registre.py` vérifie que I1 à I14 et S1 à S14 figurent ici avec leur jalon et au moins un nom de test.

Convention : un invariant `In` a son module `tests/invariants/test_iNN_<slug>.py` et des tests `test_iNN_…`. Un invariant n'est « testé » qu'une fois tous ses tests listés écrits et verts. L'ordre des jalons suit le §14. Le SPEC ne rattache les scénarios qu'aux jalons : ceux cités sous un invariant sont un rapprochement par sujet, à revoir quand le test est écrit.

## Invariants

### I1 — Vérité de l'affichage
- Énoncé : tout état affiché est observé et daté ; périmé au-delà du seuil de fraîcheur ; inconnu affiché « inconnu » ; l'état voulu n'est jamais présenté comme réel (§1.2, §9, §13 : 5 s flux, 30 s moteur).
- Jalon : M1
- Module : `tests/invariants/test_i01_verite_affichage.py`
- Tests prévus : `test_i01_etat_affiche_porte_horodatage_observation`, `test_i01_etat_perime_au_dela_du_seuil`, `test_i01_etat_inconnu_affiche_inconnu`, `test_i01_etat_voulu_jamais_presente_comme_observe`
- Scénarios : S9, S10 (aussi S1, S7)
- État : prévu

### I2 — Une seule porte
- Énoncé : toute commande vers un moteur passe par la plateforme ; interfaces natives joignables par l'adaptateur seul ou désactivées ; entrée manuelle forcée désactivée (§1.2, §13 réseau `engines`).
- Jalon : M2
- Module : `tests/invariants/test_i02_une_seule_porte.py`
- Tests prévus : `test_i02_config_generee_desactive_interfaces_natives`, `test_i02_moteur_ne_joint_que_risk_et_recepteur`, `test_i02_entree_manuelle_forcee_desactivee`
- Scénarios : S8
- État : prévu

### I3 — Mode vérifié et immuable
- Énoncé : mode fixé à la création ; mode effectif relu à chaque démarrage ; écart = entrées interdites et alerte critique ; paper et backtest ne reçoivent aucune clé de trading (§1.2, F6).
- Jalon : M2
- Module : `tests/invariants/test_i03_mode_verifie.py`
- Tests prévus : `test_i03_mode_immuable_apres_creation`, `test_i03_ecart_de_mode_interdit_les_entrees_et_alerte`, `test_i03_paper_et_backtest_sans_cle_de_trading`
- Scénarios : S7
- État : prévu

### I4 — Jamais d'obstacle à une sortie
- Énoncé : aucune panne, limite, décision de risque ni kill switch ne bloque une sortie, un stop ou une réduction (§1.2, §10).
- Jalon : M3
- Module : `tests/invariants/test_i04_sortie_jamais_bloquee.py`
- Tests prévus : `test_i04_sortie_passe_si_risk_service_en_panne`, `test_i04_sortie_passe_sous_kill_switch`, `test_i04_sortie_passe_limite_depassee` (propriétés, `risk-failclosed-testing`)
- Scénarios : S12, S3
- État : prévu

### I5 — Refus par défaut de ce qui augmente le risque
- Énoncé : entrée, renfort, hausse de limite, passage en live : doute, panne, donnée périmée ou erreur = refus (§1.2, §10).
- Jalon : M3
- Module : `tests/invariants/test_i05_refus_par_defaut.py`
- Tests prévus : `test_i05_entree_refusee_en_cas_de_timeout`, `test_i05_entree_refusee_sur_donnee_perimee`, `test_i05_reponse_malformee_du_hook_refusee`, `test_i05_hausse_de_limite_et_passage_live_refuses_en_cas_de_doute`
- Scénarios : S2, S11
- État : prévu

### I6 — Aucune entrée sans décision
- Énoncé : tout ordre d'entrée observé correspond à une décision `accept` valide ; sinon alerte critique et pause des entrées de l'instance (§1.2, §10).
- Jalon : M3
- Module : `tests/invariants/test_i06_entree_sans_decision.py`
- Tests prévus : `test_i06_entree_sans_decision_accept_leve_order_unauthorized`, `test_i06_entree_sans_decision_met_les_entrees_en_pause`, `test_i06_decision_accept_expiree_ne_couvre_pas_l_entree`
- Scénarios : S6
- État : prévu

### I7 — Position protégée
- Énoncé : toute position live a un stop actif ; un stop tenu par le moteur ne compte que si le moteur bat ; sans protection, alerte critique (§1.2, §13 : 30 s / 60 s).
- Jalon : M3
- Module : `tests/invariants/test_i07_position_protegee.py`
- Tests prévus : `test_i07_position_live_sans_stop_leve_alerte_critique`, `test_i07_stop_moteur_ne_compte_que_si_moteur_bat`, `test_i07_ordre_stop_manquant_sur_venue_alerte_en_60s`
- Scénarios : S4
- État : prévu

### I8 — Commande tracée jusqu'à l'effet
- Énoncé : une commande n'est « faite » que lorsque son effet est observé ; sinon en attente, échouée ou expirée, visiblement (§1.2, F9).
- Jalon : M1
- Module : `tests/invariants/test_i08_commande_tracee.py`
- Tests prévus : `test_i08_commande_non_faite_sans_effet_observe`, `test_i08_commande_sans_reponse_passe_timed_out`, `test_i08_cycle_de_vie_de_la_commande_est_ordonne`
- Scénarios : S10
- État : prévu

### I9 — Indépendance de la plateforme
- Énoncé : arrêt, redémarrage ou mise à jour de la plateforme ne touche aucune instance ni position ; pendant la panne, entrées refusées, sorties et stops continuent (§1.2, §13).
- Jalon : M2
- Module : `tests/invariants/test_i09_independance_plateforme.py`
- Tests prévus : `test_i09_redemarrage_plateforme_ne_redemarre_aucune_instance`, `test_i09_aucune_entree_pendant_la_panne`, `test_i09_sorties_passees_pendant_la_panne_resynchronisees_sans_doublon`
- Scénarios : S5
- État : prévu

### I10 — Empreinte de déploiement
- Énoncé : ce qui tourne est identifié par une empreinte (code, paramètres, politique de sortie, image, configuration générée) ; backtest, paper et live ne s'enchaînent qu'à empreinte identique, hors champs propres au mode (§1.2, F1).
- Jalon : M2
- Module : `tests/invariants/test_i10_empreinte.py`
- Tests prévus : `test_i10_empreinte_change_si_un_composant_change`, `test_i10_promotion_refusee_si_empreinte_differente`, `test_i10_champs_propres_au_mode_exclus_de_la_comparaison`
- Scénarios : S1, S8
- État : prévu

### I11 — Aucun ordre émis par la plateforme
- Énoncé : aucun composant de la plateforme n'appelle une fonction d'ordre d'une venue ; ses accès aux venues sont en lecture (§1.2, §13 « Contrôle de I11 »).
- Jalon : M7
- Module : `tests/invariants/test_i11_aucun_ordre_plateforme.py`
- Tests prévus : `test_i11_code_plateforme_n_atteint_aucune_fonction_d_ordre` (analyse statique des imports), `test_i11_acces_venue_en_lecture_seule`
- Scénarios : S14
- État : prévu

### I12 — Secrets à sens unique
- Énoncé : une clé saisie n'est jamais relue, affichée ni journalisée ; transmise seulement au moteur de l'instance live affectée (§1.2, F6, §13 journalisation).
- Jalon : M2
- Module : `tests/invariants/test_i12_secrets_sens_unique.py`
- Tests prévus : `test_i12_api_ne_renvoie_jamais_la_valeur_d_un_secret`, `test_i12_logs_masquent_les_valeurs_sentinelles` (livré dès M1 avec l'authentification, SPEC §14), `test_i12_cle_transmise_par_fichier_memoire_jamais_par_env`, `test_i12_cle_limitee_a_l_instance_live_affectee`
- Scénarios : aucun rattaché au §14
- État : prévu

### I13 — Noyau indépendant de la périphérie
- Énoncé : n8n, agents et Grafana arrêtés, la gouvernance, le risque, le kill switch et les alertes critiques fonctionnent (§1.2, §11).
- Jalon : M4
- Module : `tests/invariants/test_i13_noyau_independant.py`
- Tests prévus : `test_i13_risque_et_kill_switch_sans_n8n_ni_grafana_ni_agents`, `test_i13_alerte_critique_part_par_le_canal_direct`
- Scénarios : S13
- État : prévu

### I14 — Tout est audité
- Énoncé : toute action qui change un état (humain, agent, n8n, automatisme) est écrite dans le journal d'audit inaltérable, avec son auteur (§1.2).
- Jalon : M1
- Module : `tests/invariants/test_i14_audit.py`
- Tests prévus : `test_i14_toute_action_ecrit_une_ligne_d_audit_avec_auteur`, `test_i14_journal_d_audit_inalterable`, `test_i14_action_d_automatisme_attribuee_a_son_auteur`
- Scénarios : aucun ne porte directement sur l'audit ; critère « audit alimenté » du §14 M1
- État : prévu

## Scénarios de référence

Tests de bout en bout sur FakeEngine sauf mention (§14). Fichiers sous `tests/scenarios/`.

| N° | Jalon | Fichier prévu | Objet | État |
| --- | --- | --- | --- | --- |
| S1 | M2 | `tests/scenarios/test_s01_deploiement_paper.py` | Déploiement en paper, sorties seules puis entrées ouvertes | prévu |
| S2 | M3 | `tests/scenarios/test_s02_limite_depassee.py` | Limite dépassée : entrée refusée, raison visible | prévu |
| S3 | M3 | `tests/scenarios/test_s03_kill_switch_global.py` | Kill switch global sur 20 instances | prévu |
| S4 | M3 | `tests/scenarios/test_s04_moteur_plante_position_ouverte.py` | Moteur planté avec position ouverte | prévu |
| S5 | M2 | `tests/scenarios/test_s05_plateforme_arretee_5_min.py` | Plateforme arrêtée 5 minutes puis relancée | prévu |
| S6 | M3 | `tests/scenarios/test_s06_moteur_hors_de_controle.py` | Entrée sans décision, pause, arrêt du conteneur | prévu |
| S7 | M2 | `tests/scenarios/test_s07_ecart_de_mode.py` | Moteur live déclaré pour une instance paper | prévu |
| S8 | M2 | `tests/scenarios/test_s08_derive_de_configuration.py` | Configuration modifiée hors plateforme, détectée en 60 s | prévu |
| S9 | M1 | `tests/scenarios/test_s09_evenements_degrades.py` | Événements dupliqués, désordonnés ou perdus | prévu |
| S10 | M1 | `tests/scenarios/test_s10_commande_sans_reponse.py` | Commande sans réponse : `timed_out` | prévu |
| S11 | M3 | `tests/scenarios/test_s11_hook_en_erreur.py` | Hook en erreur (Freqtrade dry-run) : aucune entrée | prévu |
| S12 | M3 | `tests/scenarios/test_s12_sortie_risk_service_en_panne.py` | Sortie pendant une panne du Risk service (dry-run) | prévu |
| S13 | M4 | `tests/scenarios/test_s13_peripherie_arretee.py` | n8n, Grafana et agents arrêtés : S2 et S3 passent | prévu |
| S14 | M7 | `tests/scenarios/test_s14_repetition_live_bac_a_sable.py` | Répétition du live en bac à sable (clé fournie par l'opérateur) | prévu |
