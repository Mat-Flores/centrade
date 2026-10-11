import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Même CSP que deploy/caddy/Caddyfile : le test e2e échoue si le front viole la politique.
const csp =
  "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'";

// E2E sur la vraie pile (`make e2e-live`) : /api est relayé vers l'API locale lancée par scripts/e2e_stack.py.
// L'API n'accepte que son origine publique (CSRF) : le relais lui présente celle-ci, jamais l'origine du navigateur.
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
