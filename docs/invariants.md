# Registre des invariants et des scénarios de référence

Source : SPEC §1.2 (invariants), §14 (jalons, scénarios), §0.13. À la clôture de M2, I1, I3, I8, I10, I12, I14, S1, S7, S8, S9 et S10 sont `testé` ; I2, I9 et S5 sont `testé` avec une réserve notée à leur ligne ; le reste est un plan. L'état d'une ligne passe de `prévu` à `testé` quand le test existe et passe. `tests/invariants/test_registre.py` vérifie que I1 à I14 et S1 à S14 figurent ici avec leur jalon et au moins un nom de test.

Convention : un invariant `In` a son module `tests/invariants/test_iNN_<slug>.py` et des tests `test_iNN_…`. Un invariant n'est « testé » qu'une fois tous ses tests listés écrits et verts ; « Tests prévus » devient la liste des tests livrés quand l'invariant est `testé`. L'ordre des jalons suit le §14. Le SPEC ne rattache les scénarios qu'aux jalons : ceux cités sous un invariant sont un rapprochement par sujet, à revoir quand le test est écrit.

## Invariants

### I1 — Vérité de l'affichage
- Énoncé : tout état affiché est observé et daté ; périmé au-delà du seuil de fraîcheur ; inconnu affiché « inconnu » ; l'état voulu n'est jamais présenté comme réel (§1.2, §9, §13 : 5 s flux, 30 s moteur).
- Jalon : M1
- Module : `tests/invariants/test_i01_verite_affichage.py`
- Tests (livrés, verts) : `test_i01_etat_affiche_porte_horodatage_observation`, `test_i01_etat_perime_au_dela_du_seuil`, `test_i01_etat_inconnu_affiche_inconnu`, `test_i01_etat_voulu_jamais_presente_comme_observe`
- Scénarios : S9, S10 (aussi S1, S7)
- État : testé (M1)

### I2 — Une seule porte
- Énoncé : toute commande vers un moteur passe par la plateforme ; interfaces natives joignables par l'adaptateur seul ou désactivées ; entrée manuelle forcée désactivée (§1.2, §13 réseau `engines`).
- Jalon : M2
- Module : `tests/invariants/test_i02_une_seule_porte.py`
- Tests (livrés, verts) : `test_i02_config_generee_desactive_interfaces_natives`, `test_i02_entree_manuelle_forcee_desactivee`, `test_i02_moteur_ne_joint_que_risk_et_recepteur`
- Scénarios : S8
- État : testé (M2), avec une réserve : le refus réel de l'entrée forcée par un moteur n'est établi que par l'essai réel `tests/freqtrade_adapter/test_ft_real.py` (`test_dry_run_instance_starts_reports_trades_and_stops`), lancé en local, hors CI.

### I3 — Mode vérifié et immuable
- Énoncé : mode fixé à la création ; mode effectif relu à chaque démarrage ; écart = entrées interdites et alerte critique ; paper et backtest ne reçoivent aucune clé de trading (§1.2, F6).
- Jalon : M2
- Module : `tests/invariants/test_i03_mode_verifie.py`
- Tests (livrés, verts) : `test_i03_mode_immuable_apres_creation`, `test_i03_ecart_de_mode_interdit_les_entrees_et_alerte`, `test_i03_mode_relu_a_chaque_demarrage`, `test_i03_paper_et_backtest_sans_cle_de_trading`, `test_i03_cle_de_trading_remise_seulement_si_tout_concorde`
- Scénarios : S7
- État : testé (M2)

### I4 — Jamais d'obstacle à une sortie
- Énoncé : aucune panne, limite, décision de risque ni kill switch ne bloque une sortie, un stop ou une réduction (§1.2, §10).
- Jalon : M3
- Module : `tests/invariants/test_i04_sortie_jamais_bloquee.py`
- Tests prévus : `test_i04_sortie_passe_si_risk_service_en_panne`, `test_i04_sortie_passe_sous_kill_switch`, `test_i04_sortie_passe_limite_depassee` (propriétés, `risk-failclosed-testing`)
- Scénarios : S12, S3
- Partiel à M1 (commandes seulement, `tests/invariants/test_i04_reduction_jamais_bloquee.py`, verts) : `test_i04_commande_de_reduction_n_expire_jamais_avant_l_envoi`, `test_i04_echeance_de_la_pause_court_depuis_l_envoi`, `test_i04_panne_du_bus_n_empeche_ni_l_envoi_ni_le_releve`, `test_i04_erreur_sur_une_instance_n_empeche_pas_les_autres`, `test_i04_echec_d_ecriture_pour_une_commande_n_empeche_pas_d_envoyer_les_autres`, `test_i04_pause_envoyee_meme_si_le_moteur_etait_muet_au_tour_precedent`. Le module prévu ci-dessus reste celui de M3.
- État : prévu

### I5 — Refus par défaut de ce qui augmente le risque
- Énoncé : entrée, renfort, hausse de limite, passage en live : doute, panne, donnée périmée ou erreur = refus (§1.2, §10).
- Jalon : M3
- Module : `tests/invariants/test_i05_refus_par_defaut.py`
- Tests prévus : `test_i05_entree_refusee_en_cas_de_timeout`, `test_i05_entree_refusee_sur_donnee_perimee`, `test_i05_reponse_malformee_du_hook_refusee`, `test_i05_hausse_de_limite_et_passage_live_refuses_en_cas_de_doute`
- Scénarios : S2, S11
- Partiel à M1 (commandes seulement, `tests/invariants/test_i05_refus_par_defaut.py`, verts) : `test_i05_regle_de_refus_de_ce_qui_augmente_le_risque`, `test_i05_reprise_reverifiee_juste_avant_l_envoi`, `test_i05_reprise_perimee_ne_part_jamais`, `test_i05_l_envoi_lui_meme_ecarte_une_reprise_perimee`, `test_i05_reprise_acceptee_et_verifiee_quand_rien_ne_s_y_oppose`, `test_i05_demarrage_refuse_sauf_instance_arretee`. Le module prévu ci-dessus reste celui de M3.
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
- Tests (livrés, verts) : `test_i08_commande_non_faite_sans_effet_observe`, `test_i08_commande_sans_reponse_passe_timed_out`, `test_i08_cycle_de_vie_de_la_commande_est_ordonne`, `test_i08_pas_de_verification_sur_un_releve_anterieur_a_l_accuse`, `test_i08_pause_et_flatten_passent_devant_une_instance_occupee`, `test_i08_empreinte_d_audit_de_l_expiration_porte_le_statut_precedent`
- Scénarios : S10
- État : testé (M1)

### I9 — Indépendance de la plateforme
- Énoncé : arrêt, redémarrage ou mise à jour de la plateforme ne touche aucune instance ni position ; pendant la panne, entrées refusées, sorties et stops continuent (§1.2, §13).
- Jalon : M2
- Module : `tests/invariants/test_i09_independance_plateforme.py`
- Tests (livrés à M2, verts) : `test_i09_arret_du_worker_ne_touche_aucun_conteneur` et `test_i09_adoption_sans_redemarrage` (Docker local), `test_i09_arret_du_worker_sans_effet_sur_les_instances`, `test_i09_redemarrage_plateforme_ne_redemarre_aucune_instance`, `test_i09_sorties_passees_pendant_la_panne_resynchronisees_sans_doublon`, `test_i09_conteneur_orphelin_signale_et_intact`, `test_i09_empreinte_d_etiquette_differente_et_conteneur_manquant_signales`
- Scénarios : S5
- Reste à écrire : `test_i09_aucune_entree_pendant_la_panne`. Il tient au contrôle d'entrée du moteur quand le Risk service ne répond pas (hook de risque, M3, S11).
- État : testé (M2) pour l'indépendance et la reprise sans doublon ; partiel pour « entrées refusées pendant la panne » (M3).

### I10 — Empreinte de déploiement
- Énoncé : ce qui tourne est identifié par une empreinte (code, paramètres, politique de sortie, image, configuration générée) ; backtest, paper et live ne s'enchaînent qu'à empreinte identique, hors champs propres au mode (§1.2, F1).
- Jalon : M2
- Module : `tests/invariants/test_i10_empreinte.py`
- Tests (livrés à M2, verts) : `test_i10_meme_entree_meme_empreinte`, `test_i10_chaque_champ_change_l_empreinte`, `test_i10_le_mode_n_entre_pas_dans_l_empreinte`, `test_i10_independant_de_l_ordre_des_cles`, `test_i10_parametres_differents_empreintes_differentes`, `test_i10_image_code_ou_configuration_differents_refusent_les_entrees`, `test_i10_champs_propres_au_mode_exclus_de_la_comparaison`, `test_i10_empreinte_enregistree_au_deploiement_est_celle_de_ce_qui_tourne`
- Scénarios : S1, S8
- Reste à écrire : `test_i10_promotion_refusee_si_empreinte_differente` (la promotion arrive à M7).
- État : testé (M2). Toute clé écrite dans la configuration générée est dans l'empreinte ; la propriété d'indépendance à l'ordre des clés porte sur un JSON canonique.

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
- Tests (livrés, verts) : `tests/invariants/test_i12_secrets_sens_unique.py` (M1) : `test_i12_logs_masquent_les_valeurs_sentinelles`, `test_i12_erreur_sql_sans_les_parametres` ; `tests/invariants/test_i12_frontiere_dechiffrement.py` (M2) : `test_i12_aucun_module_de_l_api_n_importe_le_dechiffrement`, `test_i12_l_api_demarree_ne_charge_pas_le_dechiffrement`, `test_i12_la_valeur_saisie_ne_ressort_nulle_part`, `test_i12_cle_remise_au_seul_moteur_de_l_instance_live_du_compte`, `test_i12_cle_de_lecture_jamais_remise_a_un_moteur`, `test_i12_fichier_d_instance_droits_restreints_atomique_puis_supprime`, `test_i12_echec_d_ecriture_ne_laisse_aucun_fichier` ; `apps/api/tests/auth/test_logs_audit.py` : `test_i12_aucune_valeur_sensible_dans_les_logs_d_un_parcours_complet`. Côté API, aussi `tests/scenarios/test_comptes_et_cles.py` (`test_put_ecriture_seule_reponse_sans_valeur_ni_derive`).
- Scénarios : aucun rattaché au §14
- État : testé (M2). Limite connue : la frontière de déchiffrement tient par le code et un test d'import, pas par la cryptographie (ADR 0009, point 13).

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
- Tests (livrés, verts) : `test_i14_toute_action_ecrit_une_ligne_d_audit_avec_auteur`, `test_i14_journal_d_audit_inalterable`, `test_i14_action_d_automatisme_attribuee_a_son_auteur`, `test_i14_ecritures_concurrentes_sans_fourche`, `test_i14_empreinte_deterministe_et_sans_valeur` ; côté API (`apps/api/tests/auth/test_logs_audit.py`) : `test_i14_evenements_d_auth_laissent_une_ligne_d_audit_avec_auteur_et_ip`, `test_i14_mot_de_passe_correct_sans_totp_laisse_une_trace`, `test_i14_verrouillage_et_echec_sur_compte_inconnu_sont_audites`
- Scénarios : aucun ne porte directement sur l'audit ; critère « audit alimenté » du §14 M1
- État : testé (M1)

## Scénarios de référence

Tests de bout en bout sur FakeEngine sauf mention (§14). Fichiers sous `tests/scenarios/`.

| N° | Jalon | Fichier prévu | Objet | État |
| --- | --- | --- | --- | --- |
| S1 | M2 | `tests/scenarios/test_s01_deploiement_paper.py` | Déploiement en paper, sorties seules puis entrées ouvertes | testé (M2) : `test_s01_deploiement_paper_de_bout_en_bout` |
| S2 | M3 | `tests/scenarios/test_s02_limite_depassee.py` | Limite dépassée : entrée refusée, raison visible | prévu |
| S3 | M3 | `tests/scenarios/test_s03_kill_switch_global.py` | Kill switch global sur 20 instances | prévu |
| S4 | M3 | `tests/scenarios/test_s04_moteur_plante_position_ouverte.py` | Moteur planté avec position ouverte | prévu |
| S5 | M2 | `tests/scenarios/test_s05_plateforme_arretee.py` | Plateforme arrêtée 5 minutes puis relancée | testé (M2) : `test_s05_plateforme_arretee_5_minutes_puis_relancee` (indépendance et reprise sans doublon) ; partiel pour « entrées refusées pendant la panne », qui tient au hook de risque (M3) |
| S6 | M3 | `tests/scenarios/test_s06_moteur_hors_de_controle.py` | Entrée sans décision, pause, arrêt du conteneur | prévu |
| S7 | M2 | `tests/scenarios/test_s07_ecart_de_mode.py` | Moteur live déclaré pour une instance paper | testé (M2) : `test_s07_ecart_de_mode_entrees_jamais_ouvertes` |
| S8 | M2 | `tests/scenarios/test_s08_derive_de_configuration.py` | Configuration modifiée hors plateforme, détectée en 60 s | testé (M2) : `test_s08_derive_detectee_en_60_s_sorties_seules_alerte_critique`, `test_s08_cle_possedee_absente_de_la_relecture_est_une_derive` (horloge injectée ; la borne de 60 s tient depuis que le worker traite chaque instance dans sa propre tâche) |
| S9 | M1 | `tests/scenarios/test_s09_evenements_degrades.py` | Événements dupliqués, désordonnés ou perdus | testé (M1) : `test_s09_projections_exactes_apres_resynchronisation`, `test_s09_modes_enchaines_sur_une_meme_instance` |
| S10 | M1 | `tests/scenarios/test_s10_commande_sans_reponse.py` | Commande sans réponse : `timed_out` | testé (M1) : `test_s10_commande_sans_reponse_timed_out_visible_jamais_verified` |
| S11 | M3 | `tests/scenarios/test_s11_hook_en_erreur.py` | Hook en erreur (Freqtrade dry-run) : aucune entrée | prévu |
| S12 | M3 | `tests/scenarios/test_s12_sortie_risk_service_en_panne.py` | Sortie pendant une panne du Risk service (dry-run) | prévu |
| S13 | M4 | `tests/scenarios/test_s13_peripherie_arretee.py` | n8n, Grafana et agents arrêtés : S2 et S3 passent | prévu |
| S14 | M7 | `tests/scenarios/test_s14_repetition_live_bac_a_sable.py` | Répétition du live en bac à sable (clé fournie par l'opérateur) | prévu |
