# Skills et plugins par jalon

Avant de commencer un jalon (SPEC.md §14), applique la procédure d'activation ci-dessous, puis utilise en priorité les skills de la ligne du jalon.

## Procédure d'activation (début de chaque jalon)

1. Dans `.claude/settings.json`, clé `enabledPlugins` : passe à `true` les plugins « Toujours actifs » et ceux du jalon courant, et à `false` tous les autres. Ne change que ces valeurs `true`/`false` : n'ajoute ni ne retire aucune entrée, et ne touche à rien d'autre dans le fichier (hooks, permissions). Cette règle vaut demande explicite de l'opérateur au sens du SPEC §0.9, pour ces seules valeurs.
2. Donne à l'opérateur la liste de ce qui a été activé et désactivé, puis demande-lui d'exécuter `/reload-plugins` (ou de redémarrer la session). Attends sa confirmation avant de commencer le jalon. Si aucune valeur n'a changé, dis-le et continue sans attendre.
3. Si un plugin du jalon est absent de `enabledPlugins`, ne l'installe pas toi-même : donne à l'opérateur la commande `claude plugin install <nom>@<marketplace> --scope project` à exécuter dans un terminal.

### Toujours actifs

`ponytail@ponytail`, `agent-skills@addy-agent-skills`, `context7@claude-plugins-official`, `security-guidance@claude-plugins-official`, `differential-review@trailofbits`, `claude-mem@thedotmack`

`claude-mem` (ajouté par l'opérateur le 10 octobre 2026) sert à la mémoire entre les sessions. Ses skills ne remplacent aucun skill du tableau des déclencheurs ci-dessous. Son skill `cloud-sync` ne s'utilise pas sans accord explicite de l'opérateur (SPEC §17.7).

### Actifs selon le jalon

| Jalon | Plugins à `true` (en plus des « Toujours actifs ») |
| --- | --- |
| M0 | `impeccable@impeccable`, `modern-python@trailofbits`, `agentic-actions-auditor@trailofbits`, `supply-chain-risk-auditor@trailofbits`, `insecure-defaults@trailofbits` |
| M1 | `impeccable@impeccable`, `frontend-design@claude-plugins-official`, `chrome-devtools-mcp@claude-plugins-official`, `sharp-edges@trailofbits`, `property-based-testing@trailofbits`, `pg@aiguide` |
| M2 | `impeccable@impeccable`, `frontend-design@claude-plugins-official`, `chrome-devtools-mcp@claude-plugins-official`, `insecure-defaults@trailofbits`, `sharp-edges@trailofbits` |
| M3 | `property-based-testing@trailofbits`, `claude-security@claude-plugins-official`, `quantitative-trading@claude-code-workflows`, `impeccable@impeccable`, `frontend-design@claude-plugins-official`, `chrome-devtools-mcp@claude-plugins-official` |
| M4 | `n8n-mcp-skills@n8n-mcp-skills`, `insecure-defaults@trailofbits`, `impeccable@impeccable`, `frontend-design@claude-plugins-official`, `chrome-devtools-mcp@claude-plugins-official` |
| M5 | `n8n-mcp-skills@n8n-mcp-skills`, `sharp-edges@trailofbits`, `impeccable@impeccable`, `frontend-design@claude-plugins-official`, `chrome-devtools-mcp@claude-plugins-official` |
| M6 | `quantitative-trading@claude-code-workflows`, `impeccable@impeccable`, `frontend-design@claude-plugins-official`, `chrome-devtools-mcp@claude-plugins-official` |
| M7 | `claude-security@claude-plugins-official`, `static-analysis@trailofbits`, `supply-chain-risk-auditor@trailofbits`, `impeccable@impeccable` |

Les skills installés hors plugin (`shadcn`, `web-design-guidelines`, `backtest-expert`, `edge-strategy-reviewer`) sont dans `~/.claude/skills/` : ils sont toujours disponibles et ne se pilotent pas par `enabledPlugins`.

## Graphe de connaissances (clôture de chaque jalon, à partir de M1)

À la clôture de M1, puis de chaque jalon suivant, après le commit final et avant `/clear` : demande à l'opérateur d'exécuter `/graphify` pour reconstruire le graphe, et attends sa confirmation avant de déclarer le jalon clos. Ne lance pas `/graphify` toi-même.

- Pas de demande à M0 : le dépôt ne contient encore que l'ossature, lisible directement.
- En cours de jalon, quand `graphify-out/graph.json` existe, garde le graphe à jour toi-même avec `graphify update .` après tes modifications de code (CLAUDE.md).

## Skills à utiliser

**Principe.** Quand un skill couvre un besoin, c'est lui qui fait le travail : ne crée pas d'agent pour ça et ne réinvente pas sa méthode. Les seuls agents de projet sont `Explore` et `test-runner` (routage vers Haiku).

**Comment s'assurer qu'un skill entre en jeu au bon moment :**

1. Dès qu'un déclencheur du tableau ci-dessous se présente, invoque le skill avec l'outil Skill **avant** d'agir. Ne compte pas sur un déclenchement automatique.
2. Quand tu délègues un lot à un subagent, son brief nomme les skills qu'il doit invoquer. Un subagent ne voit pas ce fichier si tu ne le lui dis pas.
3. À la vérification du jalon, liste les déclencheurs rencontrés et le skill invoqué pour chacun. Un déclencheur sans skill invoqué = travail à reprendre avec le skill.
4. Si le skill voulu n'apparaît pas dans la session, son plugin est désactivé ou absent : applique la procédure d'activation, ne le remplace pas par ta propre méthode.

### Déclencheurs (obligatoires)

| Quand… | Invoque |
| --- | --- |
| L'opérateur demande de lancer un jalon | `milestone` |
| Tu poses une question sur le code existant | `graphify query` (si le graphe existe), sinon l'agent `Explore` |
| Tu découpes un jalon en lots | `agent-skills:planning-and-task-breakdown` |
| Tu implémentes un lot | `agent-skills:incremental-implementation` et `agent-skills:test-driven-development` |
| Tu vas coder contre une bibliothèque, un moteur ou une image | `agent-skills:source-driven-development` + `context7` (doc du tag épinglé) |
| Tu conçois une route, un contrat ou un schéma d'événement | `agent-skills:api-and-interface-design` |
| Tu ajoutes une dépendance | `supply-chain-risk-auditor`, puis ADR avec `agent-skills:documentation-and-adrs` |
| Le code touche entrées utilisateur, auth, sessions, secrets ou intégration externe | `agent-skills:security-and-hardening`, `insecure-defaults` |
| Le code touche risque, kill switch, réconciliation, watchdog, commandes ou SecretStore | `risk-failclosed-testing`, `property-based-testing`, `agent-skills:doubt-driven-development` |
| Tu touches `packages/adapters/freqtrade/` ou `strategies/` | `freqtrade-adapter` |
| Tu crées ou restyles un écran | `impeccable`, `frontend-design`, `shadcn`, `agent-skills:frontend-ui-engineering` |
| Tu crées un graphique, une jauge ou une tuile de chiffres | `dataviz` |
| Tu vérifies un écran qui tourne | `agent-skills:browser-testing-with-devtools`, `web-design-guidelines` |
| Tu écris un backtest, une stratégie ou le rapport de fiabilité | `backtest-hygiene`, `backtest-expert`, `edge-strategy-reviewer` |
| Tu écris un workflow n8n | `n8n-mcp-skills` |
| Tu écris un workflow GitHub Actions | `agent-skills:ci-cd-and-automation`, `agentic-actions-auditor` |
| Tu ajoutes logs, métriques ou alertes | `agent-skills:observability-and-instrumentation` |
| Tu écris du code qui appelle l'API Claude ou un serveur MCP | `claude-api` |
| Un test échoue ou un build casse | `agent-skills:debugging-and-error-recovery` |
| Les lots du jalon sont finis (revue, contexte neuf) | agents `agent-skills:security-auditor` et `agent-skills:code-reviewer`, avec `differential-review` et `/security-review` dans leur brief |
| Tu écris un test d'invariant (`test_iNN_…`) ou un scénario de référence (S1 à S14) | `agent-skills:test-driven-development` ; pour I4 à I7, `risk-failclosed-testing` |
| Tu crées ou modifies un écran qui montre un état de moteur | règles de vérité de l'affichage du SPEC §9, avec `agent-skills:frontend-ui-engineering` |
| Tu clos le jalon | `agent-skills:shipping-and-launch` |

### Accent par jalon

Ce tableau dit sur quoi porter l'effort à chaque jalon ; les déclencheurs ci-dessus restent valables à tous les jalons.

| Jalon | Skills à utiliser | Pour quoi |
| --- | --- | --- |
| M0 | `impeccable` (l'opérateur lance `/impeccable init` → `PRODUCT.md`, puis `/impeccable document` → `DESIGN.md`), `shadcn`, `modern-python`, `agentic-actions-auditor`, `supply-chain-risk-auditor`, `insecure-defaults`, `agent-skills:ci-cd-and-automation` | Jetons de design, socle uv/ruff, workflows GitHub, dépendances, valeurs par défaut de Compose ; rédiger le modèle de menaces ; initialiser `docs/invariants.md` |
| M1 | `frontend-design`, `impeccable`, `shadcn`, `web-design-guidelines`, `dataviz`, `agent-skills:browser-testing-with-devtools`, `sharp-edges`, `property-based-testing`, `pg` | Cockpit et captures de référence ; auth, TOTP, RBAC ; idempotence des événements ; hypertables ; états voulu et observé, cycle des commandes, modes de panne du FakeEngine, règles de vérité de l'affichage (I1, I8, I14) |
| M2 | `context7` (Freqtrade, `freqtrade-client`, SDK Docker), `insecure-defaults`, `sharp-edges`, `agent-skills:api-and-interface-design`, skill de projet `freqtrade-adapter` | SecretStore, runner Docker, adaptateur ; écrans Stratégies et Ordres avec les skills de design de M1 ; configuration générée et relue, empreinte, démarrage en sorties seules, gabarit de conteneur, adoption (I2, I3, I9, I10, I12) ; revérifier l'annexe C du SPEC sur le tag épinglé |
| M3 | `property-based-testing`, `agent-skills:doubt-driven-development`, `claude-security`, `quantitative-trading`, skill de projet `risk-failclosed-testing` | Invariants du §10, tests de chaos, scan approfondi ; code critique délégué sur Opus (SPEC §17.2) ; écran Risque avec les skills de design de M1 ; protection des positions, réconciliation étendue, script de secours (I4, I5, I6, I7) |
| M4 | `n8n-mcp-skills` (documentation seule, aucun identifiant n8n), `agent-skills:observability-and-instrumentation`, `insecure-defaults` | WF-01, WF-06, WF-07, `make n8n-lint`, métriques et traces ; écran Flow avec les skills de design de M1 ; surveillance externe, panneau « Garanties » (I13) |
| M5 | `n8n-mcp-skills`, `claude-api`, `sharp-edges` | WF-02 à WF-05, serveur MCP, corpus d'injection, évals, prompt caching ; écrans Agents (lecture) et Journal et rapports avec les skills de design de M1 |
| M6 | `backtest-expert`, `edge-strategy-reviewer`, `quantitative-trading`, skill de projet `backtest-hygiene`, `dataviz` | Rapport de fiabilité F8, revue quantitative en contexte neuf, courbes d'equity ; écrans Agents et Backtests avec les skills de design de M1 |
| M7 | `claude-security`, `static-analysis`, `supply-chain-risk-auditor`, `differential-review`, `agent-skills:shipping-and-launch`, `impeccable` (audit, polish) | Revue de sécurité finale, durcissement, runbooks, finition de l'interface ; liste blanche des sorties réseau des moteurs, répétition en bac à sable (I11, S14) |

## Interdits

- Aucun skill, plugin ou serveur MCP capable de passer un ordre ou de déplacer des fonds (SPEC §17.7).
- Les skills de trading servent à relire l'hygiène des backtests, jamais à concevoir une stratégie rentable (SPEC §0.6).
- Les skills de projet (`milestone`, `freqtrade-adapter`, `risk-failclosed-testing`, `backtest-hygiene`) sont dans `.claude/skills/` : ils sont fournis, ne les réécris pas.
