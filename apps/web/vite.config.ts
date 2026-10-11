import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Même CSP que deploy/caddy/Caddyfile : le test e2e échoue si le front viole la politique.
const csp =
  "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  build: { assetsInlineLimit: 0 },
  preview: { headers: { "Content-Security-Policy": csp } },
  test: { include: ["src/**/*.test.{ts,tsx}"] },
});
