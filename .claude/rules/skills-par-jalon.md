# Skills et plugins par jalon

Avant de commencer un jalon (SPEC.md §14), repère sa ligne ci-dessous et utilise ces skills en priorité.
Un skill absent de la session n'est pas installé : signale-le à l'opérateur, ne l'installe pas toi-même (SPEC §0.9).
Ne garde actifs que les plugins du jalon courant (SPEC §17.4) ; propose à l'opérateur de désactiver les autres.

## Toujours

| Moment | Skill |
| --- | --- |
| Question sur le code | `graphify query` avant toute recherche brute |
| Découper un jalon | `agent-skills:plan`, puis `agent-skills:build` lot par lot |
| Toute logique nouvelle | `agent-skills:test` (TDD) |
| API d'une bibliothèque ou d'un moteur | `context7` : vérifier la doc du tag épinglé avant de coder |
| Fin de jalon, par un agent qui n'a pas écrit le code | `/security-review`, `differential-review`, `agent-skills:review` |
| Clôture de jalon | `agent-skills:ship` |

## Par jalon

| Jalon | Skills à utiliser | Pour quoi |
| --- | --- | --- |
| M0 | `impeccable` (teach → `PRODUCT.md`, `DESIGN.md`), `shadcn`, `modern-python`, `agentic-actions-auditor`, `supply-chain-risk-auditor`, `insecure-defaults`, `agent-skills:ci-cd-and-automation` | Jetons de design, socle uv/ruff, workflows GitHub, dépendances, valeurs par défaut de Compose ; rédiger le modèle de menaces |
| M1 | `frontend-design`, `impeccable`, `shadcn`, `web-design-guidelines`, `dataviz`, `agent-skills:browser-testing-with-devtools`, `sharp-edges`, `property-based-testing`, `pg` | Cockpit et captures de référence ; auth, TOTP, RBAC ; idempotence des événements ; hypertables |
| M2 | `context7` (Freqtrade, `freqtrade-client`, SDK Docker), `insecure-defaults`, `sharp-edges`, `agent-skills:api-and-interface-design`, skill de projet `freqtrade-adapter` | SecretStore, runner Docker, adaptateur ; écrans Stratégies et Ordres avec les skills de design de M1 |
| M3 | `property-based-testing`, `agent-skills:doubt-driven-development`, `claude-security`, `quantitative-trading`, skill de projet `risk-failclosed-testing` | Invariants du §10, tests de chaos, scan approfondi ; code confié à `risk-engineer` (Opus) |
| M4 | `n8n-mcp-skills` (documentation seule, aucun identifiant n8n), `agent-skills:observability-and-instrumentation`, `insecure-defaults` | WF-01, WF-06, WF-07, `make n8n-lint`, métriques et traces |
| M5 | `n8n-mcp-skills`, `claude-api`, `sharp-edges` | WF-02 à WF-05, serveur MCP, corpus d'injection, évals, prompt caching |
| M6 | `backtest-expert`, `edge-strategy-reviewer`, `quantitative-trading`, skill de projet `backtest-hygiene`, `dataviz` | Rapport de fiabilité F8, revue par `quant-reviewer`, courbes d'equity |
| M7 | `claude-security`, `static-analysis`, `supply-chain-risk-auditor`, `differential-review`, `agent-skills:shipping-and-launch`, `impeccable` (audit, polish) | Revue de sécurité finale, durcissement, runbooks, finition de l'interface |

## Interdits

- Aucun skill, plugin ou serveur MCP capable de passer un ordre ou de déplacer des fonds (SPEC §17.7).
- Les skills de trading servent à relire l'hygiène des backtests, jamais à concevoir une stratégie rentable (SPEC §0.6).
- Les skills de projet (`freqtrade-adapter`, `risk-failclosed-testing`, `backtest-hygiene`) sont à écrire dans `.claude/skills/` au jalon où ils servent.
