// Single source of the Content-Security-Policy served by `vite preview`: it must equal deploy/caddy/Caddyfile
// (csp.test.ts compares them), so the e2e run fails if the front end violates the production policy.
export const CSP =
  "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'";
