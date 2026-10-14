# Registre des invariants et des scénarios de référence

Source : SPEC §1.2 (invariants), §14 (jalons, scénarios), §0.13. À la clôture de M2, I1, I3, I8, I10, I12, I14, S1, S7, S8, S9 et S10 sont `testé` ; I2, I9 et S5 sont `testé` avec une réserve notée à leur ligne ; le reste est un plan. L'état d'une ligne passe de `prévu` à `testé` quand le test existe et passe. `tests/invariants/test_registry.py` vérifie que I1 à I14 et S1 à S14 figurent ici avec leur jalon et au moins un nom de test.

Convention : un invariant `In` a son module `tests/invariants/test_iNN_<slug>.py` et des tests `test_iNN_…`. Un invariant n'est « testé » qu'une fois tous ses tests listés écrits et verts ; « Tests prévus » devient la liste des tests livrés quand l'invariant est `testé`. L'ordre des jalons suit le §14. Le SPEC ne rattache les scénarios qu'aux jalons : ceux cités sous un invariant sont un rapprochement par sujet, à revoir quand le test est écrit.

## Invariants

### I1 — Vérité de l'affichage
- Énoncé : tout état affiché est observé et daté ; périmé au-delà du seuil de fraîcheur ; inconnu affiché « inconnu » ; l'état voulu n'est jamais présenté comme réel (§1.2, §9, §13 : 5 s flux, 30 s moteur).
- Jalon : M1
- Module : `tests/invariants/test_i01_display_truth.py`
- Tests (livrés, verts) : `test_i01_displayed_state_carries_observation_timestamp`, `test_i01_state_is_stale_beyond_threshold`, `test_i01_unknown_state_is_displayed_as_unknown`, `test_i01_desired_state_is_never_shown_as_observed`, `test_i01_aggregates_are_unknown_when_engine_never_observed`, `test_i01_aggregates_are_stale_beyond_threshold` ; réconciliation des agrégats de la liste avec `GET /trades` : `tests/properties/test_instance_aggregates.py::test_list_aggregates_equal_the_decimal_sums_of_the_instance_trades`, `test_i01_balance_never_observed_is_unknown_not_zero`, `test_i01_balance_is_stale_beyond_threshold` ; projection des soldes : `tests/properties/test_balance_projection.py` (`test_replayed_or_shuffled_snapshots_keep_one_row_per_currency_from_the_latest`, `test_an_older_snapshot_never_overwrites_a_newer_balance`, `test_a_currency_absent_from_the_snapshot_is_deleted`)
- Agrégats de la liste des instances (PnL réalisé par devise, trades clos, positions ouvertes) : datés par `instances.observed_at` quand l'état est connu, sinon par la dernière observation des positions restantes (donc périmés), sinon « inconnu » (valeur `None`, jamais 0). Le PnL réalisé est net de frais, comme le contrat moteur (`ClosedTrade.pnl`) ; le FakeEngine y est aligné (avant : brut).
- Soldes (`balances` de la liste et du détail, table `balance_snapshots`, dernière valeur par instance et devise, sans historique) : datés par le plus ancien `observed_at` de leurs lignes ; moteur injoignable = dernière valeur gardée, périmée ; aucun solde observé, ou dernier relevé sans solde = « inconnu » (valeur `None`), jamais 0. Un relevé plus ancien n'écrase ni ne supprime un solde plus récent ; limite connue : après un relevé sans aucun solde, un relevé plus ancien arrivé en retard peut réécrire ses lignes (avec leur date ancienne, donc périmées). Le FakeEngine produit un solde USDT déterministe (1000 + PnL réalisé, `free` = `total`).
- Scénarios : S9, S10 (aussi S1, S7)
- État : testé (M1)

### I2 — Une seule porte
- Énoncé : toute commande vers un moteur passe par la plateforme ; interfaces natives joignables par l'adaptateur seul ou désactivées ; entrée manuelle forcée désactivée (§1.2, §13 réseau `engines`).
- Jalon : M2
- Module : `tests/invariants/test_i02_single_door.py`
- Tests (livrés, verts) : `test_i02_generated_config_disables_native_interfaces`, `test_i02_manual_entry_is_forced_off`, `test_i02_engine_reaches_only_risk_and_receiver`
- Scénarios : S8
- État : testé (M2), avec une réserve : le refus réel de l'entrée forcée par un moteur n'est établi que par l'essai réel `tests/freqtrade_adapter/test_ft_real.py` (`test_dry_run_instance_starts_reports_trades_and_stops`), lancé en local, hors CI.

### I3 — Mode vérifié et immuable
- Énoncé : mode fixé à la création ; mode effectif relu à chaque démarrage ; écart = entrées interdites et alerte critique ; paper et backtest ne reçoivent aucune clé de trading (§1.2, F6).
- Jalon : M2
- Module : `tests/invariants/test_i03_mode_verified.py`
- Tests (livrés, verts) : `test_i03_mode_is_immutable_after_creation`, `test_i03_mode_mismatch_forbids_entries_and_raises_an_alert`, `test_i03_mode_is_reread_at_every_start`, `test_i03_paper_and_backtest_never_get_a_trading_key`, `test_i03_trading_key_is_handed_only_if_everything_matches`
- Scénarios : S7
- État : testé (M2)

### I4 — Jamais d'obstacle à une sortie
- Énoncé : aucune panne, limite, décision de risque ni kill switch ne bloque une sortie, un stop ou une réduction (§1.2, §10).
- Jalon : M3
- Module : `tests/invariants/test_i04_exit_never_blocked.py`
- Tests prévus : `test_i04_exit_goes_through_when_the_risk_service_is_down`, `test_i04_exit_goes_through_under_the_kill_switch`, `test_i04_exit_goes_through_when_a_limit_is_exceeded` (propriétés, `risk-failclosed-testing`)
- Scénarios : S12, S3
- Partiel à M1 (commandes seulement, `tests/invariants/test_i04_reduction_never_blocked.py`, verts) : `test_i04_risk_reducing_command_never_expires_before_dispatch`, `test_i04_pause_deadline_runs_from_dispatch`, `test_i04_bus_outage_blocks_neither_dispatch_nor_snapshot`, `test_i04_error_on_one_instance_does_not_block_the_others`, `test_i04_write_failure_for_one_command_does_not_block_dispatching_the_others`, `test_i04_pause_is_dispatched_even_if_engine_was_silent_on_previous_tick`, `test_i04_balance_projection_failure_keeps_positions_and_dispatch` (la projection des soldes s'écrit dans son propre SAVEPOINT : son échec n'empêche ni les positions, ni les ordres, ni les commandes). Le module prévu ci-dessus reste celui de M3.
- État : prévu

### I5 — Refus par défaut de ce qui augmente le risque
- Énoncé : entrée, renfort, hausse de limite, passage en live : doute, panne, donnée périmée ou erreur = refus (§1.2, §10).
- Jalon : M3
- Module : `tests/invariants/test_i05_default_refusal.py`
- Tests prévus : `test_i05_entry_is_rejected_on_timeout`, `test_i05_entry_is_rejected_on_stale_data`, `test_i05_malformed_hook_response_is_rejected`, `test_i05_limit_increase_and_live_promotion_are_rejected_when_in_doubt`
- Scénarios : S2, S11
- Partiel à M1 (commandes seulement, `tests/invariants/test_i05_default_refusal.py`, verts) : `test_i05_risk_increasing_actions_are_rejected_by_default`, `test_i05_resume_is_rechecked_just_before_dispatch`, `test_i05_stale_resume_is_never_dispatched`, `test_i05_dispatch_itself_drops_a_stale_resume`, `test_i05_resume_is_accepted_and_verified_when_nothing_opposes_it`, `test_i05_start_is_rejected_unless_the_instance_is_stopped`. Le module prévu ci-dessus reste celui de M3.
- État : prévu

### I6 — Aucune entrée sans décision
- Énoncé : tout ordre d'entrée observé correspond à une décision `accept` valide ; sinon alerte critique et pause des entrées de l'instance (§1.2, §10).
- Jalon : M3
- Module : `tests/invariants/test_i06_entry_without_decision.py`
- Tests prévus : `test_i06_entry_without_accept_decision_raises_order_unauthorized`, `test_i06_entry_without_decision_pauses_entries`, `test_i06_expired_accept_decision_does_not_cover_the_entry`
- Scénarios : S6
- État : prévu

### I7 — Position protégée
- Énoncé : toute position live a un stop actif ; un stop tenu par le moteur ne compte que si le moteur bat ; sans protection, alerte critique (§1.2, §13 : 30 s / 60 s).
- Jalon : M3
- Module : `tests/invariants/test_i07_protected_position.py`
- Tests prévus : `test_i07_live_position_without_stop_raises_a_critical_alert`, `test_i07_engine_held_stop_counts_only_while_the_engine_heartbeats`, `test_i07_missing_stop_order_on_venue_raises_an_alert_within_60s`
- Scénarios : S4
- État : prévu

### I8 — Commande tracée jusqu'à l'effet
- Énoncé : une commande n'est « faite » que lorsque son effet est observé ; sinon en attente, échouée ou expirée, visiblement (§1.2, F9).
- Jalon : M1
- Module : `tests/invariants/test_i08_command_traced.py`
- Tests (livrés, verts) : `test_i08_command_is_not_done_without_an_observed_effect`, `test_i08_command_without_response_becomes_timed_out`, `test_i08_command_lifecycle_is_ordered`, `test_i08_no_verification_on_snapshot_older_than_the_ack`, `test_i08_pause_and_flatten_go_through_a_busy_instance`, `test_i08_expiry_audit_fingerprint_carries_the_previous_status`
- Scénarios : S10
- État : testé (M1)

### I9 — Indépendance de la plateforme
- Énoncé : arrêt, redémarrage ou mise à jour de la plateforme ne touche aucune instance ni position ; pendant la panne, entrées refusées, sorties et stops continuent (§1.2, §13).
- Jalon : M2
- Module : `tests/invariants/test_i09_platform_independence.py`
- Tests (livrés à M2, verts) : `test_i09_worker_shutdown_touches_no_container` et `test_i09_adoption_does_not_restart_the_container` (Docker local), `test_i09_worker_shutdown_has_no_effect_on_instances`, `test_i09_platform_restart_restarts_no_instance`, `test_i09_exits_made_during_outage_are_resynced_without_duplicates`, `test_i09_orphan_container_is_reported_and_left_intact`, `test_i09_different_label_fingerprint_and_missing_container_are_reported`
- Scénarios : S5
- Reste à écrire : `test_i09_no_entry_happens_during_the_outage`. Il tient au contrôle d'entrée du moteur quand le Risk service ne répond pas (hook de risque, M3, S11).
- État : testé (M2) pour l'indépendance et la reprise sans doublon ; partiel pour « entrées refusées pendant la panne » (M3).

### I10 — Empreinte de déploiement
- Énoncé : ce qui tourne est identifié par une empreinte (code, paramètres, politique de sortie, image, configuration générée) ; backtest, paper et live ne s'enchaînent qu'à empreinte identique, hors champs propres au mode (§1.2, F1).
- Jalon : M2
- Module : `tests/invariants/test_i10_fingerprint.py`
- Tests (livrés à M2, verts) : `test_i10_same_input_gives_same_fingerprint`, `test_i10_each_field_changes_the_fingerprint`, `test_i10_mode_is_not_part_of_the_fingerprint`, `test_i10_fingerprint_is_independent_of_key_order`, `test_i10_different_params_give_different_fingerprints`, `test_i10_different_image_code_or_config_rejects_entries`, `test_i10_mode_specific_fields_are_excluded_from_comparison`, `test_i10_fingerprint_recorded_at_deploy_is_that_of_what_runs`
- Scénarios : S1, S8
- Reste à écrire : `test_i10_promotion_is_rejected_when_the_fingerprint_differs` (la promotion arrive à M7).
- État : testé (M2). Toute clé écrite dans la configuration générée est dans l'empreinte ; la propriété d'indépendance à l'ordre des clés porte sur un JSON canonique.

### I11 — Aucun ordre émis par la plateforme
- Énoncé : aucun composant de la plateforme n'appelle une fonction d'ordre d'une venue ; ses accès aux venues sont en lecture (§1.2, §13 « Contrôle de I11 »).
- Jalon : M7
- Module : `tests/invariants/test_i11_no_platform_order.py`
- Tests prévus : `test_i11_platform_code_reaches_no_order_function` (analyse statique des imports), `test_i11_venue_access_is_read_only`
- Scénarios : S14
- État : prévu

### I12 — Secrets à sens unique
- Énoncé : une clé saisie n'est jamais relue, affichée ni journalisée ; transmise seulement au moteur de l'instance live affectée (§1.2, F6, §13 journalisation).
- Jalon : M2
- Module : `tests/invariants/test_i12_secrets_one_way.py`
- Tests (livrés, verts) : `tests/invariants/test_i12_secrets_one_way.py` (M1) : `test_i12_logs_mask_sentinel_values`, `test_i12_sql_error_omits_parameters` ; `tests/invariants/test_i12_decryption_boundary.py` (M2) : `test_i12_no_api_module_imports_decryption`, `test_i12_started_api_does_not_load_decryption`, `test_i12_entered_value_appears_nowhere`, `test_i12_key_is_handed_only_to_the_engine_of_the_accounts_live_instance`, `test_i12_read_key_is_never_handed_to_an_engine`, `test_i12_instance_file_is_restricted_atomic_then_deleted`, `test_i12_write_failure_leaves_no_file` ; `apps/api/tests/auth/test_logs_audit.py` : `test_i12_no_sensitive_value_in_logs_of_a_full_journey`. Côté API, aussi `tests/scenarios/test_accounts_and_keys.py` (`test_put_is_write_only_and_response_has_no_value_or_derivative`).
- Scénarios : aucun rattaché au §14
- État : testé (M2). Limite connue : la frontière de déchiffrement tient par le code et un test d'import, pas par la cryptographie (ADR 0009, point 13).

### I13 — Noyau indépendant de la périphérie
- Énoncé : n8n, agents et Grafana arrêtés, la gouvernance, le risque, le kill switch et les alertes critiques fonctionnent (§1.2, §11).
- Jalon : M4
- Module : `tests/invariants/test_i13_independent_core.py`
- Tests prévus : `test_i13_risk_and_kill_switch_work_without_n8n_grafana_or_agents`, `test_i13_critical_alert_goes_out_through_the_direct_channel`
- Scénarios : S13
- État : prévu

### I14 — Tout est audité
- Énoncé : toute action qui change un état (humain, agent, n8n, automatisme) est écrite dans le journal d'audit inaltérable, avec son auteur (§1.2).
- Jalon : M1
- Module : `tests/invariants/test_i14_audit.py`
- Tests (livrés, verts) : `test_i14_every_action_writes_an_audit_row_with_its_author`, `test_i14_audit_log_is_tamper_proof`, `test_i14_automation_action_is_attributed_to_its_author`, `test_i14_concurrent_writes_do_not_fork_the_chain`, `test_i14_fingerprint_is_deterministic_and_carries_no_value` ; côté API (`apps/api/tests/auth/test_logs_audit.py`) : `test_i14_auth_events_leave_an_audit_row_with_author_and_ip`, `test_i14_correct_password_without_totp_leaves_a_trace`, `test_i14_lockout_and_failure_on_unknown_account_are_audited`
- Scénarios : aucun ne porte directement sur l'audit ; critère « audit alimenté » du §14 M1
- État : testé (M1)

## Scénarios de référence

Tests de bout en bout sur FakeEngine sauf mention (§14). Fichiers sous `tests/scenarios/`.

| N° | Jalon | Fichier prévu | Objet | État |
| --- | --- | --- | --- | --- |
| S1 | M2 | `tests/scenarios/test_s01_paper_deployment.py` | Déploiement en paper, sorties seules puis entrées ouvertes | testé (M2) : `test_s01_paper_deployment_end_to_end` |
| S2 | M3 | `tests/scenarios/test_s02_limit_exceeded.py` | Limite dépassée : entrée refusée, raison visible | prévu |
| S3 | M3 | `tests/scenarios/test_s03_global_kill_switch.py` | Kill switch global sur 20 instances | prévu |
| S4 | M3 | `tests/scenarios/test_s04_engine_crash_with_open_position.py` | Moteur planté avec position ouverte | prévu |
| S5 | M2 | `tests/scenarios/test_s05_platform_outage.py` | Plateforme arrêtée 5 minutes puis relancée | testé (M2) : `test_s05_platform_outage_of_5_minutes_then_restart` (indépendance et reprise sans doublon) ; partiel pour « entrées refusées pendant la panne », qui tient au hook de risque (M3) |
| S6 | M3 | `tests/scenarios/test_s06_engine_out_of_control.py` | Entrée sans décision, pause, arrêt du conteneur | prévu |
| S7 | M2 | `tests/scenarios/test_s07_mode_mismatch.py` | Moteur live déclaré pour une instance paper | testé (M2) : `test_s07_mode_mismatch_never_opens_entries` |
| S8 | M2 | `tests/scenarios/test_s08_config_drift.py` | Configuration modifiée hors plateforme, détectée en 60 s | testé (M2) : `test_s08_drift_detected_within_60_s_exits_only_critical_alert`, `test_s08_owned_key_missing_from_the_reread_is_drift` (horloge injectée ; la borne de 60 s tient depuis que le worker traite chaque instance dans sa propre tâche) |
| S9 | M1 | `tests/scenarios/test_s09_degraded_events.py` | Événements dupliqués, désordonnés ou perdus | testé (M1) : `test_s09_projections_are_exact_after_resync`, `test_s09_chained_modes_on_the_same_instance` |
| S10 | M1 | `tests/scenarios/test_s10_unanswered_command.py` | Commande sans réponse : `timed_out` | testé (M1) : `test_s10_unanswered_command_is_timed_out_visible_never_verified` |
| S11 | M3 | `tests/scenarios/test_s11_hook_error.py` | Hook en erreur (Freqtrade dry-run) : aucune entrée | prévu |
| S12 | M3 | `tests/scenarios/test_s12_exit_during_risk_service_outage.py` | Sortie pendant une panne du Risk service (dry-run) | prévu |
| S13 | M4 | `tests/scenarios/test_s13_periphery_stopped.py` | n8n, Grafana et agents arrêtés : S2 et S3 passent | prévu |
| S14 | M7 | `tests/scenarios/test_s14_live_sandbox_rehearsal.py` | Répétition du live en bac à sable (clé fournie par l'opérateur) | prévu |
