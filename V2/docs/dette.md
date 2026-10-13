# Dette connue

Défauts repérés et volontairement laissés en l'état, avec la raison. Une ligne sort de ce fichier quand elle est corrigée.

| Date | Sujet | Constat | Pourquoi ce n'est pas corrigé |
| --- | --- | --- | --- |
| 2026-10-13 | `tests/test_worker_parallele.py::test_ce_qui_reduit_le_risque_part_avant_ce_qui_l_augmente` | Échoue parfois quand toute la suite tourne (machine chargée), passe quand son fichier tourne seul. Observé une fois sur une suite complète de `V2/` ; trois exécutions isolées réussies. | Le test porte sur l'ordre des commandes du worker (ce qui réduit le risque avant ce qui l'augmente). L'analyser demande de distinguer un délai de test trop court d'un vrai défaut d'ordonnancement : reporté après la fusion, sur décision de l'opérateur. |
