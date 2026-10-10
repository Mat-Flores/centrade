---
name: milestone
description: Run one milestone (M0-M7) of SPEC.md end to end with delegation, gates and independent reviews. Use when the operator asks to launch, start, run or resume a milestone ("lance le jalon M0").
argument-hint: [M0|M1|M2|M3|M4|M5|M6|M7]
---

# Milestone $ARGUMENTS

You are the orchestrator (Opus). Do not write bulk code yourself. Run only the milestone the operator named; never chain to the next one. If no milestone was named, ask which one.

**Skills first.** When an installed skill covers a need, the skill does the work: invoke it with the Skill tool before acting, and do not create an agent or improvise a method for it. The trigger table in `.claude/rules/skills-par-jalon.md` is mandatory. Keep a running list of `trigger -> skill invoked`; you report it at step 7.

Planned stops: this protocol asks the operator to act at steps 0, 8 and sometimes 4. Everywhere else, apply SPEC.md §15 defaults and keep going; ask only when truly blocked.

0. **Prepare.**
   - Read SPEC.md in full (§0.1), then `.claude/rules/skills-par-jalon.md`.
   - Apply its activation procedure (plugin `true`/`false` values), tell the operator what changed and ask them to run `/reload-plugins`. If nothing changed, say so and continue without waiting.
   - Check the tools this milestone needs with `command -v` (docker, uv, pnpm, make, gitleaks, pre-commit, semgrep, gh). For each missing one, give the operator the install command and continue with the work that does not depend on it. Do not install system tools yourself.
   - Create the branch `jalon/<mx>` from `main` if it does not exist, and work there.
1. **Frame.** Read the row for $ARGUMENTS in SPEC.md §14 and the sections it cites. Create one task per acceptance criterion, per invariant (I1-I14) and per reference scenario (S1-S14) attached to this milestone in §14. State your assumptions in one short list. The invariants of SPEC §1.2 override any other requirement: if a feature conflicts with one, the invariant wins and you tell the operator.
2. **Explore.** Ask the `Explore` agent for the repo state relevant to this milestone (one call). List what already exists so you do not recreate it: `CLAUDE.md` and `.claude/` are provided by the operator — verify them, never rewrite them.
3. **Plan.** Invoke `agent-skills:planning-and-task-breakdown`. Split into independent work packages (max 3 in parallel). For each package write a brief with: goal, files, SPEC.md section, acceptance test, what NOT to touch, **the skills to invoke** (from the trigger table, by exact name), and the model.
4. **Build.** Delegate each package to the built-in `general-purpose` agent, passing the model explicitly: `sonnet` for ordinary packages; `opus` with high effort for risk, secrets, auth, kill switch and reconciliation. Each brief starts with "Invoke these skills before coding: …". Commit per coherent package on the milestone branch. Interactive skills (`/impeccable init`, `/impeccable document`) are run by the operator: ask for them when PRODUCT.md or DESIGN.md is needed.
5. **Gate.** The `test-runner` agent runs `make lint test`. On failure the fixing agent invokes `agent-skills:debugging-and-error-recovery`. Up to 3 fix iterations; then escalate to yourself.
6. **Independent reviews, in parallel, each in a fresh context and read-only by instruction.**
   - Always: `agent-skills:security-auditor` and `agent-skills:code-reviewer` on `git diff main...HEAD`. Their brief tells them to invoke `differential-review`, `/security-review` and the security skills active for this milestone, and to check docs/security/threat-model.md.
   - If trading or backtest logic: `general-purpose` (sonnet, high effort) invoking `backtest-hygiene`, `backtest-expert`, `edge-strategy-reviewer`.
   - If UI: `general-purpose` (sonnet) invoking `agent-skills:browser-testing-with-devtools` and `web-design-guidelines`; light and dark themes, 1280 px and tablet, keyboard, `axe`.
   Fix every BLOCK, critical or high finding. Re-run the gate.
7. **Verify.**
   - For each acceptance criterion, show evidence (command and result, test name, screenshot path). No criterion is done without evidence. A criterion only the operator can check (`/doctor`) is listed as "to confirm by the operator".
   - "CI green" needs a run on GitHub: ask the operator to authorize pushing the milestone branch (`git push -u origin jalon/<mx>`, never the default branch), then read the result with `gh run list` and `gh run view`. Without authorization or without `gh`, run the same checks locally and list the criterion as "to confirm by the operator".
   - Skill check: go through the trigger table; for every trigger this milestone hit, name the skill that was invoked and by whom. A trigger with no skill invoked means that part is redone with the skill.
   - Invariant check: every invariant attached to this milestone has a passing test named `test_iNN_…` under tests/invariants/, and every attached scenario passes under tests/scenarios/. Update docs/invariants.md.
   - Update docs/security/threat-model.md.
8. **Close.** Invoke `agent-skills:shipping-and-launch`. Docs and migrations current; `docker compose up` smoke test; clean commits; append cost notes to docs/agentic/couts.md. Report in 15 lines max: criteria met with evidence, criteria not met and why, what the operator must do. Then ask the operator to run, in this order: `/graphify` (from M1 onward), then `/clear`. Do not push or merge unless asked.

Never skip a gate to save tokens. Never run anything in live mode. Never install tools with order-execution capability. Never edit `.claude/settings.json` (except the `enabledPlugins` values of step 0) or `.claude/hooks/`.
