---
paths:
  - apps/web/**
---

- Read PRODUCT.md and DESIGN.md before creating or restyling a screen.
- Design tokens only; both themes derive from the same tokens; tinted neutrals, never pure black/gray.
- Tabular numerals for every number; one accent color; red only for LIVE and danger.
- No gradients, no cards inside cards, no bounce/elastic easing; transitions <= 150 ms; honor prefers-reduced-motion.
- Loading, empty and error states on every view; WCAG 2.2 AA; full keyboard use.
- French UI strings live in translation files. Develop against FakeEngine.
- Before finishing: `npx impeccable detect apps/web/src` clean of primary findings; Playwright + axe pass.
