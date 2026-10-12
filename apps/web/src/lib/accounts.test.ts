import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import {
  AccountSchema,
  accountFormErrors,
  errorCause,
  labelMatches,
  permissionState,
  TOTP_CODE,
  totpCause,
  writeKey,
  type Account,
} from "./accounts";

const SENTINEL = "TEST-SECRET-DO-NOT-USE";
const valid = { label: "Principal", venue: "binance", type: "live", environment: "sandbox", currency: "usdt", capital_cap: "1500.50" };

const account = (over: Partial<Account> = {}): Account => ({
  id: "a1",
  venue: "binance",
  type: "live",
  environment: "production",
  label: "Principal",
  currency: "USDT",
  capital_cap: "1500.50",
  trade_key: null,
  read_key: null,
  permissions_verified_at: null,
  ip_restricted: null,
  created_at: "2026-10-11T15:00:00Z",
  updated_at: "2026-10-11T15:00:00Z",
  ...over,
});

afterEach(() => vi.unstubAllGlobals());

describe("formulaire de compte", () => {
  it("accepte un compte valide, devise en majuscules, plafond gardé en chaîne", () => {
    const { data, fields } = accountFormErrors(valid);
    expect(fields).toEqual([]);
    expect(data?.currency).toBe("USDT");
    expect(data?.capital_cap).toBe("1500.50"); // jamais converti : zéro final conservé
  });

  it("refuse libellé vide, venue invalide, devise invalide", () => {
    expect(accountFormErrors({ ...valid, label: "  " }).fields).toEqual(["label"]);
    expect(accountFormErrors({ ...valid, venue: "Binance!" }).fields).toEqual(["venue"]);
    expect(accountFormErrors({ ...valid, currency: "u" }).fields).toEqual(["currency"]);
  });

  it.each(["0", "0.00", "-5", "1e3", "1,5", "abc", "1.0000000000000000001", "12345678901234567890"])(
    "refuse le plafond %s",
    (cap) => expect(accountFormErrors({ ...valid, capital_cap: cap }).fields).toEqual(["capital_cap"]),
  );

  it("un plafond vide signifie aucun plafond", () => {
    expect(accountFormErrors({ ...valid, capital_cap: "" }).fields).toEqual([]);
  });
});

describe("confirmation par saisie du libellé", () => {
  it("exige le libellé exact", () => {
    expect(labelMatches("Principal", "Principal")).toBe(true);
    expect(labelMatches("  Principal ", "Principal")).toBe(true);
    expect(labelMatches("principal", "Principal")).toBe(false);
    expect(labelMatches("", "Principal")).toBe(false);
  });
});

describe("permissions", () => {
  it("un compte paper n'a rien à vérifier", () => expect(permissionState(account({ type: "paper" })).kind).toBe("none"));
  it("live sans clé de trading", () => expect(permissionState(account()).kind).toBe("no-key"));
  it("clé sans date de vérification : non vérifiées", () => {
    const key = { usage: "trade", key_version: 1, stored_at: "x", rotated_at: null, last_used_at: null } as const;
    expect(permissionState(account({ trade_key: key })).kind).toBe("unverified");
    expect(permissionState(account({ trade_key: key, permissions_verified_at: "2026-10-11T15:00:00Z" })).kind).toBe("verified");
  });
});

describe("causes d'échec", () => {
  const problem = (status: number, detail: string) => new ApiError("problem", status, { detail }, detail);
  it("403 TOTP, 409 refus, réseau", () => {
    expect(errorCause(problem(403, "Confirmation par code TOTP requise.")).cause).toBe("totp");
    expect(errorCause(problem(403, "Interdit.")).cause).toBe("forbidden");
    expect(errorCause(problem(409, "Un compte paper ne reçoit aucune clé.")).cause).toBe("refused");
    expect(errorCause(new ApiError("network", null, null, "x")).cause).toBe("network");
    expect(errorCause(new Error("x")).cause).toBe("other");
  });
});

describe("la valeur d'une clé ne survit pas à l'envoi", () => {
  it("n'entre dans aucun cache de requêtes et la réponse ne peut pas la ramener", async () => {
    const qc = new QueryClient();
    const sent: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        sent.push(String(init.body));
        // Même si un serveur fautif renvoyait la valeur, le schéma Zod la retire.
        return new Response(
          JSON.stringify({ usage: "trade", key_version: 1, stored_at: "2026-10-11T15:00:00Z", rotated_at: null, last_used_at: null, secret: SENTINEL }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }),
    );

    const out = await writeKey("a1", "put", { usage: "trade", key: SENTINEL, secret: SENTINEL });
    qc.setQueryData(["accounts"], out);

    expect(sent[0]).toContain(SENTINEL); // elle part bien vers l'API...
    expect(JSON.stringify(out)).not.toContain(SENTINEL);
    expect(JSON.stringify(qc.getQueryCache().getAll().map((q) => q.state))).not.toContain(SENTINEL);
    expect(qc.getMutationCache().getAll()).toHaveLength(0); // ... et nulle part ailleurs
  });

  it("le schéma de compte ne porte aucun champ de valeur", () => {
    expect(Object.keys(AccountSchema.shape)).not.toContain("secret");
    expect(Object.keys(AccountSchema.shape)).not.toContain("key");
  });
});

describe("confirmation TOTP", () => {
  it("accepte six chiffres exactement", () => {
    expect(["123456", "000000"].every((c) => TOTP_CODE.test(c))).toBe(true);
    expect(["12345", "1234567", "12345a", " 123456", ""].some((c) => TOTP_CODE.test(c))).toBe(false);
  });
  it("nomme la cause de chaque réponse, sans jamais confondre un refus de code et une session perdue", () => {
    const err = (status: number) => new ApiError("problem", status, null, "x");
    expect([403, 423, 429, 401, 500].map((s) => totpCause(err(s)))).toEqual(["refused", "locked", "rateLimited", "session", "other"]);
    expect(totpCause(new ApiError("network", null, null, "x"))).toBe("network");
    expect(totpCause(new Error("x"))).toBe("other");
  });
});
