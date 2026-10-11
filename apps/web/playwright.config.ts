import { defineConfig } from "@playwright/test";

// `mock` : API simulée par page.route, sert le build (dist/) avec la CSP de production
// (`pnpm build` doit précéder `pnpm e2e`). C'est le projet de la CI.
// `live` : vraie pile jetable lancée par scripts/e2e_stack.py (`make e2e-live`, E2E_LIVE=1) ;
// le front est servi par `vite preview` (même CSP) avec un relais de /api vers l'API locale.
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
