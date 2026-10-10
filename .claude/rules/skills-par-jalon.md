# Skills et plugins par jalon

Avant de commencer un jalon (SPEC.md §14), applique la procédure d'activation ci-dessous, puis utilise en priorité les skills de la ligne du jalon.

## Procédure d'activation (début de chaque jalon)

1. Dans `.claude/settings.json`, clé `enabledPlugins` : passe à `true` les plugins « Toujours actifs » et ceux du jalon courant, et à `false` tous les autres. Ne change que ces valeurs `true`/`false` : n'ajoute ni ne retire aucune entrée, et ne touche à rien d'autre dans le fichier (hooks, permissions). Cette règle vaut demande explicite de l'opérateur au sens du SPEC §0.9, pour ces seules valeurs.
2. Donne à l'opérateur la liste de ce qui a été activé et désactivé, puis demande-lui d'exécuter `/reload-plugins` (ou de redémarrer la session). Attends sa confirmation avant de commencer le jalon.
3. Si un plugin du jalon est absent de `enabledPlugins`, ne l'installe pas toi-même : donne à l'opérateur la commande `claude plugin install <nom>@<marketplace> --scope project` à exécuter dans un terminal.

### Toujours actifs

`ponytail@ponytail`, `agent-skills@addy-agent-skills`, `context7@claude-plugins-official`, `security-guidance@claude-plugins-official`, `differential-review@trailofbits`

### Actifs selon le jalon

| Jalon | Plugins à `true` (en plus des « Toujours actifs ») |
| --- | --- |
| M0 | `impeccable@impeccable`, `modern-python@trailofbits`, `agentic-actions-auditor@trailofbits`, `supply-chain-risk-auditor@trailofbits`, `insecure-defaults@trailofbits` |
| M1 | `impeccable@impeccable`, `frontend-design@claude-plugins-official`, `chrome-devtools-mcp@claude-plugins-official`, `sharp-edges@trailofbits`, `property-based-testing@trailofbits`, `pg@aiguide` |
| M2 | `impeccable@impeccable`, `frontend-design@claude-plugins-official`, `chrome-devtools-mcp@claude-plugins-official`, `insecure-defaults@trailofbits`, `sharp-edges@trailofbits` |
| M3 | `property-based-testing@trailofbits`, `claude-security@claude-plugins-official`, `quantitative-trading@claude-code-workflows`, `impeccable@impeccable`, `frontend-design@claude-plugins-official`, `chrome-devtools-mcp@claude-plugins-official` |
| M4 | `n8n-mcp-skills@n8n-mcp-skills`, `insecure-defaults@trailofbits`, `impeccable@impeccable`, `frontend-design@claude-plugins-official`, `chrome-devtools-mcp@claude-plugins-official` |
| M5 | `n8n-mcp-skills@n8n-mcp-skills`, `sharp-edges@trailofbits` |
| M6 | `quantitative-trading@claude-code-workflows`, `impeccable@impeccable`, `frontend-design@claude-plugins-official`, `chrome-devtools-mcp@claude-plugins-official` |
| M7 | `claude-security@claude-plugins-official`, `static-analysis@trailofbits`, `supply-chain-risk-auditor@trailofbits`, `impeccable@impeccable` |

Les skills installés hors plugin (`shadcn`, `web-design-guidelines`, `backtest-expert`, `edge-strategy-reviewer`) sont dans `~/.claude/skills/` : ils sont toujours disponibles et ne se pilotent pas par `enabledPlugins`.

## Graphe de connaissances (clôture de chaque jalon, à partir de M1)

À la clôture de M1, puis de chaque jalon suivant, après le commit final et avant `/clear` : demande à l'opérateur d'exécuter `/graphify` pour reconstruire le graphe, et attends sa confirmation avant de déclarer le jalon clos. Ne lance pas `/graphify` toi-même.

- Pas de demande à M0 : le dépôt ne contient encore que l'ossature, lisible directement.
- En cours de jalon, quand `graphify-out/graph.json` existe, garde le graphe à jour toi-même avec `graphify update .` après tes modifications de code (CLAUDE.md).

## Skills à utiliser

### Toujours

| Moment | Skill |
| --- | --- |
| Question sur le code | `graphify query` avant toute recherche brute |
| Découper un jalon | `agent-skills:plan`, puis `agent-skills:build` lot par lot |
| Toute logique nouvelle | `agent-skills:test` (TDD) |
| API d'une bibliothèque ou d'un moteur | `context7` : vérifier la doc du tag épinglé avant de coder |
| Fin de jalon, par un agent qui n'a pas écrit le code | `/security-review`, `differential-review`, `agent-skills:review` |
| Clôture de jalon | `agent-skills:ship` |

### Par jalon

| Jalon | Skills à utiliser | Pour quoi |
| --- | --- | --- |
| M0 | `impeccable` (teach → `PRODUCT.md`, `DESIGN.md`), `shadcn`, `modern-python`, `agentic-actions-auditor`, `supply-chain-risk-auditor`, `insecure-defaults`, `agent-skills:ci-cd-and-automation` | Jetons de design, socle uv/ruff, workflows GitHub, dépendances, valeurs par défaut de Compose ; rédiger le modèle de menaces |
| M1 | `frontend-design`, `impeccable`, `shadcn`, `web-design-guidelines`, `dataviz`, `agent-skills:browser-testing-with-devtools`, `sharp-edges`, `property-based-testing`, `pg` | Cockpit et captures de référence ; auth, TOTP, RBAC ; idempotence des événements ; hypertables |
| M2 | `context7` (Freqtrade, `freqtrade-client`, SDK Docker), `insecure-defaults`, `sharp-edges`, `agent-skills:api-and-interface-design`, skill de projet `freqtrade-adapter` | SecretStore, runner Docker, adaptateur ; écrans Stratégies et Ordres avec les skills de design de M1 |
| M3 | `property-based-testing`, `agent-skills:doubt-driven-development`, `claude-security`, `quantitative-trading`, skill de projet `risk-failclosed-testing` | Invariants du §10, tests de chaos, scan approfondi ; code confié à `risk-engineer` (Opus) ; écran Risque avec les skills de design de M1 |
| M4 | `n8n-mcp-skills` (documentation seule, aucun identifiant n8n), `agent-skills:observability-and-instrumentation`, `insecure-defaults` | WF-01, WF-06, WF-07, `make n8n-lint`, métriques et traces ; écran Flow avec les skills de design de M1 |
| M5 | `n8n-mcp-skills`, `claude-api`, `sharp-edges` | WF-02 à WF-05, serveur MCP, corpus d'injection, évals, prompt caching |
| M6 | `backtest-expert`, `edge-strategy-reviewer`, `quantitative-trading`, skill de projet `backtest-hygiene`, `dataviz` | Rapport de fiabilité F8, revue par `quant-reviewer`, courbes d'equity ; écrans Agents et Backtests avec les skills de design de M1 |
| M7 | `claude-security`, `static-analysis`, `supply-chain-risk-auditor`, `differential-review`, `agent-skills:shipping-and-launch`, `impeccable` (audit, polish) | Revue de sécurité finale, durcissement, runbooks, finition de l'interface |

## Interdits

- Aucun skill, plugin ou serveur MCP capable de passer un ordre ou de déplacer des fonds (SPEC §17.7).
- Les skills de trading servent à relire l'hygiène des backtests, jamais à concevoir une stratégie rentable (SPEC §0.6).
- Les skills de projet (`freqtrade-adapter`, `risk-failclosed-testing`, `backtest-hygiene`) sont à écrire dans `.claude/skills/` au jalon où ils servent.
