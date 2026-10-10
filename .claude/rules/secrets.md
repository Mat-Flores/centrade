---
paths:
  - apps/api/**/secret*
  - apps/api/**/accounts*
  - deploy/**
  - .github/**
---

- Secrets only via Docker secrets / SecretStore; never in env files committed, images, logs, tests or fixtures.
- Exchange keys reach an engine only as a read-only file mounted from memory, removed when the instance stops; never as an environment variable. Paper and backtest instances receive no key (SPEC F6, I3, I12).
- The trading key is used by the platform only to verify its permissions; reconciliation uses the optional read key.
- Secret values are write-only through the API and never returned.
- GitHub Actions: pin actions by SHA, minimal `permissions:`, no secrets exposed to forks, no `pull_request_target` with untrusted checkout.
- Use dummy sentinel values in tests (e.g. `TEST-SECRET-DO-NOT-USE`) and assert they never appear in logs.
