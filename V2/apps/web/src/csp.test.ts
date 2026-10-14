import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { CSP } from "./csp";

describe("preview CSP", () => {
  it("is exactly the Content-Security-Policy of deploy/caddy/Caddyfile", () => {
    const caddyfile = readFileSync(path.resolve(import.meta.dirname, "../../../deploy/caddy/Caddyfile"), "utf8");
    const match = /Content-Security-Policy\s+"([^"]+)"/.exec(caddyfile);
    expect(match?.[1]).toBe(CSP);
  });
});
