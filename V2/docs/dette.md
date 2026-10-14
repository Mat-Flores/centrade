# Dette connue

Défauts repérés et volontairement laissés en l'état, avec la raison. Une ligne sort de ce fichier quand elle est corrigée.

| Date | Sujet | Constat | Pourquoi ce n'est pas corrigé |
| --- | --- | --- | --- |
| 2026-10-13 | `tests/test_worker_parallel.py::test_risk_reducing_actions_go_out_before_risk_increasing_ones` | Échoue parfois quand toute la suite tourne (machine chargée), passe quand son fichier tourne seul. Observé une fois sur une suite complète de `V2/` ; trois exécutions isolées réussies. | Le test porte sur l'ordre des commandes du worker (ce qui réduit le risque avant ce qui l'augmente). L'analyser demande de distinguer un délai de test trop court d'un vrai défaut d'ordonnancement : reporté après la fusion, sur décision de l'opérateur. |
| 2026-10-13 | `tests/properties/test_event_idempotence.py::test_losing_some_events_does_not_corrupt_projections` | A échoué une fois sur une suite complète, puis réussi seul et sur la suite complète suivante. La trace du premier échec n'a pas été relevée. | Cause non établie. À reproduire sous charge et à analyser avec le test du worker ci-dessus, après la fusion. |
| 2026-10-13 | Suite complète, instabilité générale | Sur sept exécutions complètes de la suite dans `V2/`, trois ont eu exactement un échec, à chaque fois effacé par une relance ; les exécutions par dossier passent toujours. Deux des tests en cause sont identifiés ci-dessus, le troisième n'a pas été relevé. | Même traitement : à reproduire sous charge après la fusion. Tant que ce n'est pas fait, un échec isolé sur la suite complète se confirme par une relance avant d'être imputé à un changement. |
| 2026-10-14 | `tests/test_worker.py::test_unreachable_engine_is_unknown_and_values_are_not_refreshed` | A échoué une fois dans un lot de tests ciblés, puis réussi seul et sur la suite complète (1010 passés). | Même famille que les instabilités ci-dessus : à reproduire sous charge après la fusion. |
