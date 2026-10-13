# Supply Chain Risk Report — `rework-ui`

**Scanned:** `.`  
**Manifests read:** `package.json`  
**Scanned at:** 2026-10-12T21:14:13+00:00  
**Direct dependencies:** 16 (npm 16)

## Summary

- **No known advisory affects any of the 16 direct dependencies**, checked at the versions this project resolves.
- Transitive dependencies were **not examined**: no lockfile resolves the transitive tree (package-lock.json, uv.lock, or a go 1.17+ go.mod).
- 5 of 16 dependencies carry at least one finding, 2 of which reach production.
- Weakest coverage: **Publisher concentration**, established for 7 of 16; the Coverage section lists every criterion.

## Production dependencies

8 dependencies are declared as runtime dependencies and ship in the built artifact. Advisory status is given for every one, clean or not.

| Dependency | Version | Advisories | Other findings |
|---|---|---|---|
| `@fontsource-variable/archivo` | 5.3.0 | none known | — |
| `@fontsource-variable/martian-mono` | 5.3.0 | none known | — |
| `@gsap/react` | 2.1.2 | none known | Publisher concentration |
| `gsap` | 3.15.0 | none known | Publisher concentration |
| `lightweight-charts` | 5.2.1 | none known | — |
| `motion` | 13.4.4 | none known | — |
| `react` | 18.3.1 | none known | — |
| `react-dom` | 18.3.1 | none known | — |

## Findings

### Reaches production

| Dependency | Version | Weekly downloads | Findings |
|---|---|---|---|
| `@gsap/react` | 2.1.2 | 1,592,658/wk | single human publisher (greensock) of 1 listed |
| `gsap` | 3.15.0 | 5,990,964/wk | single human publisher (greensock) of 1 listed |

### Build-time only

Declared as development dependencies. A compromise here reaches build and CI hosts rather than users of the shipped artifact.

| Dependency | Version | Weekly downloads | Findings |
|---|---|---|---|
| `@types/react` | 18.3.31 | 171,576,209/wk | single human publisher (types) of 1 listed |
| `@types/react-dom` | 18.3.7 | 146,837,238/wk | single human publisher (types) of 1 listed |

## Upstream repository and CI hygiene — OpenSSF Scorecard

These criteria describe each dependency's own repository, not the audited
project. Remediation, where any exists, is upstream.

### Build-time only

Declared as development dependencies. A compromise here reaches build and CI hosts rather than users of the shipped artifact.

| Dependency | Version | Weekly downloads | Findings |
|---|---|---|---|
| `vite` | 8.3.4 | 196,390,084/wk | Binary-Artifacts scores 1/10 (below 10) |

## Transitive advisories

Not examined: no lockfile resolves the transitive tree (package-lock.json, uv.lock, or a go 1.17+ go.mod). Commit a lockfile to close this gap.

## Informational

Measured, not flagged.

- **CI token permissions**: median 9/10 across 8 scored dependencies; 2 score below 6. Not flagged — this measures whether CI workflows declare least-privilege tokens, which tracks project maturity rather than the likelihood of malicious code being published.
- **Changes reviewed by a second person**: median 7/10 across 9 scored dependencies; 4 score below 6. Not flagged — this measures the share of recent commits reviewed by a second person, which is low for most small single-maintainer projects and largely restates publisher concentration.
- **Publish provenance**: 9 of 16 publish with build provenance.
  Without: `@gsap/react`, `@types/react`, `@types/react-dom`, `gsap`, `lightweight-charts`, `motion`, `typescript`
- **Security policy published**: 9 of 16 publish a security policy.
  Without: `@fontsource-variable/archivo`, `@fontsource-variable/martian-mono`, `@gsap/react`, `@tailwindcss/vite`, `lightweight-charts`, `motion`, `tailwindcss`
- **Download volume**: established for 16 of 16; median 125,766,874/week. Lowest: `@fontsource-variable/martian-mono` (39,973/wk), `@fontsource-variable/archivo` (436,646/wk), `lightweight-charts` (1,231,050/wk).

## Coverage

What was and was not measured, per criterion.

| Criterion | Tier | Assessed | Flagged | Not assessable |
|---|---|---|---|---|
| Known advisories | A | 16/16 | 0 | 0 |
| Deprecated or yanked | A | 16/16 | 0 | 0 |
| Repository archived | A | 16/16 | 0 | 0 |
| Maintenance activity | A | 16/16 | 0 | 0 |
| Publisher concentration | B | 7/16 | 4 | 9 |
| Install-time script execution | B | 16/16 | 0 | 0 |
| Dangerous CI workflow | scorecard | 8/16 | 0 | 8 |
| CI token permissions | scorecard | 8/16 | 0 | 8 |
| Checked-in binaries | scorecard | 9/16 | 1 | 7 |
| Changes reviewed by a second person | scorecard | 9/16 | 0 | 7 |
| Publish provenance | info | 16/16 | 0 | 0 |
| Security policy published | info | 16/16 | 0 | 0 |
| Download volume | info | 16/16 | 0 | 0 |

## Not assessable

**Checked-in binaries**

- 7 dependencies — OpenSSF Scorecard has no report for this repository: `@fontsource-variable/archivo`, `@fontsource-variable/martian-mono`, `@gsap/react`, `motion`, `react`, `react-dom` and 1 more

**Changes reviewed by a second person**

- 7 dependencies — OpenSSF Scorecard has no report for this repository: `@fontsource-variable/archivo`, `@fontsource-variable/martian-mono`, `@gsap/react`, `motion`, `react`, `react-dom` and 1 more

**Dangerous CI workflow**

- 7 dependencies — OpenSSF Scorecard has no report for this repository: `@fontsource-variable/archivo`, `@fontsource-variable/martian-mono`, `@gsap/react`, `motion`, `react`, `react-dom` and 1 more
- 1 dependency — Scorecard could not evaluate Dangerous-Workflow (score -1): `gsap`

**Publisher concentration**

- 9 dependencies — publishes from CI with provenance, so the effective publisher set is whoever can merge to the release branch — not externally observable: `@fontsource-variable/archivo`, `@fontsource-variable/martian-mono`, `@tailwindcss/vite`, `@vitejs/plugin-react`, `react`, `react-dom` and 3 more

**CI token permissions**

- 7 dependencies — OpenSSF Scorecard has no report for this repository: `@fontsource-variable/archivo`, `@fontsource-variable/martian-mono`, `@gsap/react`, `motion`, `react`, `react-dom` and 1 more
- 1 dependency — Scorecard could not evaluate Token-Permissions (score -1): `gsap`

## Method and caveats

- pnpm-lock.yaml is present but not read: direct-dependency versions fall back to manifest pins or the latest release, and its transitive tree was not examined.
- Repository-level criteria (archived, maintenance activity, security policy, and the Scorecard checks) describe the source repository rather than the package. 16 dependencies resolve to 12 distinct repositories, so one repository can appear as several findings. Shared: github.com/DefinitelyTyped/DefinitelyTyped, github.com/fontsource/font-files, github.com/react/react, github.com/tailwindlabs/tailwindcss
- Optional tooling detected: npm. Not installed, so not used: bundler-audit, cargo-audit, osv-scanner, pip-audit.
- Direct dependencies only. Advisories attach to the package that ships the affected code, so an umbrella package can look clean while its components are not — rails 5.0.0 reports 0 advisories where actionpack 5.0.0 reports 10. Transitive dependencies were not examined: no lockfile resolves the transitive tree (package-lock.json, uv.lock, or a go 1.17+ go.mod).
- HTTP sources: 6 fetched, 117 served from cache (oldest 0.2h old), 0 refetched as stale, 0 unavailable offline, 0 errors.
