import { z } from "zod";

import { ApiError, apiFetch } from "./api";

export type LoginFailure =
  | { ok: false; cause: "refused" | "locked" | "rate-limited" | "network" | "unexpected" }
  | { ok: false; cause: "http"; status: number };
export type LoginResult = { ok: true } | LoginFailure;

const PasswordStep = z.object({ totp_required: z.literal(true) });

function failureOf(error: unknown): LoginFailure {
  if (!(error instanceof ApiError)) throw error;
  if (error.kind === "network") return { ok: false, cause: "network" };
  if (error.kind === "invalid-response") return { ok: false, cause: "unexpected" };
  const status = error.status ?? 0;
  if (status === 401 || status === 403) return { ok: false, cause: "refused" };
  if (status === 423) return { ok: false, cause: "locked" };
  if (status === 429) return { ok: false, cause: "rate-limited" };
  return { ok: false, cause: "http", status };
}

/**
 * Step 1: the password. `ok` means "the TOTP code is now requested": the session only exists
 * after `submitTotp`. The password is neither kept nor returned in the result.
 */
export async function submitLogin(
  credentials: { username: string; password: string },
  fetchImpl: typeof fetch = fetch,
): Promise<LoginResult> {
  try {
    await apiFetch("/auth/login", PasswordStep, { method: "POST", body: credentials, authCall: true, fetchImpl });
    return { ok: true };
  } catch (error) {
    return failureOf(error);
  }
}

/** Step 2: 6-digit code or recovery code. */
export async function submitTotp(code: string, fetchImpl: typeof fetch = fetch): Promise<LoginResult> {
  try {
    await apiFetch("/auth/totp", z.unknown(), { method: "POST", body: { code: code.trim() }, authCall: true, fetchImpl });
    return { ok: true };
  } catch (error) {
    return failureOf(error);
  }
}
