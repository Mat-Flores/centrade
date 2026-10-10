import { defineConfig } from "@playwright/test";

// Sert le build (dist/) avec la CSP de production : `pnpm build` doit précéder `pnpm e2e`.
export default defineConfig({
  testDir: "e2e",
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:4173", locale: "fr-CA" },
  webServer: {
    command: "pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
  },
});
