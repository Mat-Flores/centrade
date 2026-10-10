---
paths:
  - apps/web/**
---

- Read PRODUCT.md and DESIGN.md before creating or restyling a screen.
- Display truth rules (SPEC §9, I1, I8): show the observed state with its age; mark stale values as stale and unknown states as unknown, never as the last known value; show desired and observed side by side when they differ; no optimistic UI for engine commands (a button is done only when the command is `verified`).
- Never add paper, sandbox and live figures together; label every paper figure as simulated.
- In degraded mode (live stream down, core component down) only risk-reducing actions stay enabled.
- No third-party resources: fonts, scripts and styles are served by the platform; strict CSP; number format fr-CA with explicit sign and currency.
- Design tokens only; both themes derive from the same tokens; tinted neutrals, never pure black/gray.
- Tabular numerals for every number; one accent color; red only for LIVE and danger.
- No gradients, no cards inside cards, no bounce/elastic easing; transitions <= 150 ms; honor prefers-reduced-motion.
- Loading, empty and error states on every view; WCAG 2.2 AA; full keyboard use.
- French UI strings live in translation files. Develop against FakeEngine.
- Before finishing: `npx impeccable detect apps/web/src` clean of primary findings; Playwright + axe pass.
