# Coût par jalon

Rempli par l'orchestrateur à la clôture de chaque jalon (SPEC §17.4, source : `/usage`).

| Jalon | Date | Coût | Remarques |
| --- | --- | --- | --- |
| M0 | 2026-10-10 | Coût en dollars non relevé : à lire par l'opérateur avec `/usage`. Sous-agents : environ 0,98 M de tokens sur 10 délégations (5 lots Sonnet, 2 revues Opus, 1 revue d'interface Sonnet, Explore et test-runner Haiku) ; session principale non mesurée. | Les deux revues Opus pèsent 0,28 M ; le lot front 0,16 M. Une limite de session a interrompu le premier passage du test-runner. |
| M1 | 2026-10-11 | Coût en dollars non relevé : à lire par l'opérateur avec `/usage`. Sous-agents : environ 3,3 M de tokens sur 20 délégations mesurées (8 lots Sonnet, 2 lots Opus, 2 revues Opus, 1 revue d'interface Sonnet, 1 lot de documentation Sonnet, 6 passages du test-runner Haiku) ; Explore et session principale non mesurés. | Les plus lourds : auth sur Opus (0,35 M), Cockpit (0,33 M), corrections backend sur Opus (0,33 M), les deux revues Opus (0,55 M). Une limite de session a interrompu le lot D1, repris avec son contexte. Les revues ont coûté autant qu'un gros lot et ont trouvé 2 constats élevés. |
