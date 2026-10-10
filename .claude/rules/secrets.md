---
paths:
  - apps/api/**/secret*
  - apps/api/**/accounts*
  - deploy/**
  - .github/**
---

- Secrets only via Docker secrets / SecretStore; never in env files committed, images, logs, tests or fixtures.
- Secret values are write-only through the API and never returned.
- GitHub Actions: pin actions by SHA, minimal `permissions:`, no secrets exposed to forks, no `pull_request_target` with untrusted checkout.
- Use dummy sentinel values in tests (e.g. `TEST-SECRET-DO-NOT-USE`) and assert they never appear in logs.
