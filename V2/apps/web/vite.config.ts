import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Same CSP as deploy/caddy/Caddyfile: the e2e run fails if the front end violates the policy.
const csp =
  "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'";

// Live e2e on the real stack (`make e2e-live`): /api is relayed to the local API started by scripts/e2e_stack.py.
// The API only accepts its public origin (CSRF): the relay presents that origin, never the browser one.
const apiTarget = process.env.E2E_API_URL;
const publicOrigin = process.env.E2E_PUBLIC_ORIGIN ?? "https://localhost:8443";
const proxy = apiTarget
  ? {
      "/api": {
        target: apiTarget,
        changeOrigin: false,
        configure: (p: { on: (e: "proxyReq", f: (req: { setHeader: (k: string, v: string) => void }) => void) => void }) =>
          p.on("proxyReq", (req) => req.setHeader("origin", publicOrigin)),
      },
    }
  : undefined;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  build: { assetsInlineLimit: 0 },
  server: { proxy },
  preview: { headers: { "Content-Security-Policy": csp }, proxy },
  test: { include: ["src/**/*.test.{ts,tsx}"] },
});
