---
paths:
  - n8n/**
---

- n8n is peripheral: no order path, no scopes `orders:*`, `limits:write`, `secrets:*`, `kill-switch:release`.
- Every workflow: signature verification on inbound webhooks, dedup on X-Event-Id, timeouts, 3 retries with backoff, Idempotency-Key on writes.
- Credentials are created in n8n, never in JSON. No real n8n API key in the dev environment; validate workflow JSON offline.
- Run `make n8n-lint` before committing.
