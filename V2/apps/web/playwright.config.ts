import { defineConfig } from "@playwright/test";

// `mock`: API simulated with page.route, serves the build (dist/) with the production CSP
// (`pnpm build` must precede `pnpm e2e`). This is the CI project.
// `live`: disposable real stack started by scripts/e2e_stack.py (`make e2e-live`, E2E_LIVE=1);
// the front end is served by `vite preview` (same CSP) with /api relayed to the local API.
const live = process.env.E2E_LIVE === "1";
const port = live ? 4174 : 4173;

export default defineConfig({
  testDir: "e2e",
  reporter: "list",
  use: { baseURL: `http://${live ? "localhost" : "127.0.0.1"}:${port}`, locale: "fr-CA" },
  projects: [
    { name: "mock", testIgnore: /live\.spec\.ts/ },
    { name: "live", testMatch: /live\.spec\.ts/, timeout: 90_000 },
  ],
  webServer: {
    command: `pnpm exec vite preview --host ${live ? "localhost" : "127.0.0.1"} --port ${port} --strictPort`,
    url: `http://${live ? "localhost" : "127.0.0.1"}:${port}`,
    reuseExistingServer: false,
  },
});
