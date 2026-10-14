import { z } from "zod";

import { fr } from "@/i18n/fr";

/** The only network entry point of the front end: same origin, no third-party URL (CSP `connect-src 'self'`). */
export const API_BASE = "/api/v1";

const ProblemSchema = z.object({
  type: z.string().optional(),
  title: z.string().optional(),
  status: z.number().optional(),
  // A list of reasons (a rejected version upload, 422) or a plain text.
  detail: z.union([z.string(), z.array(z.string())]).optional(),
});
type RawProblem = z.infer<typeof ProblemSchema>;
/** `detail` is always a text; `reasons` keeps the list when the API sends one. */
export type Problem = Omit<RawProblem, "detail"> & { detail?: string; reasons?: string[] };

export type ApiErrorKind = "network" | "problem" | "invalid-response";

/** The single API error: network down, RFC 7807 problem (or bare HTTP error) or out-of-contract response. */
export class ApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    readonly status: number | null,
    readonly problem: Problem | null,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let onUnauthorized: (() => void) | null = null;

/** Called on any 401 (except authentication calls): the session is gone, back to login. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

export interface ApiRequest {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  /** Headers on top of the defaults (e.g. the `Idempotency-Key` of a command). */
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** Authentication calls read the 401 themselves (credentials refused): no return to login. */
  authCall?: boolean;
  fetchImpl?: typeof fetch;
}

async function readProblem(response: Response): Promise<Problem | null> {
  if (!(response.headers.get("content-type") ?? "").includes("json")) return null;
  try {
    const parsed = ProblemSchema.safeParse(await response.json());
    if (!parsed.success) return null;
    const { detail, ...rest } = parsed.data;
    return Array.isArray(detail) ? { ...rest, detail: detail.join(" ; "), reasons: detail } : { ...rest, detail };
  } catch {
    return null;
  }
}

/** Calls `/api/v1{path}` and only returns data that matches the Zod schema. */
export async function apiFetch<S extends z.ZodType>(
  path: string,
  schema: S,
  { method = "GET", body, headers, signal, authCall = false, fetchImpl = fetch }: ApiRequest = {},
): Promise<z.infer<S>> {
  let response: Response;
  try {
    response = await fetchImpl(`${API_BASE}${path}`, {
      method,
      headers: {
        accept: "application/json, application/problem+json",
        ...(body === undefined ? {} : { "content-type": "application/json" }),
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
      signal,
    });
  } catch (cause) {
    if (signal?.aborted) throw cause; // deliberate cancellation (TanStack Query), not an outage
    throw new ApiError("network", null, null, fr.errors.apiUnreachable);
  }

  if (!response.ok) {
    if (response.status === 401 && !authCall) onUnauthorized?.();
    const problem = await readProblem(response);
    throw new ApiError(
      "problem",
      response.status,
      problem,
      problem?.title ?? problem?.detail ?? fr.errors.http(response.status),
    );
  }

  let data: unknown;
  if (response.status !== 204) {
    // A 2xx that is not JSON (HTML fallback of a file server) is not an API response.
    if (!(response.headers.get("content-type") ?? "").includes("application/json")) {
      throw new ApiError("invalid-response", response.status, null, fr.errors.notJson);
    }
    try {
      data = await response.json();
    } catch {
      throw new ApiError("invalid-response", response.status, null, fr.errors.unreadableJson);
    }
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    throw new ApiError("invalid-response", response.status, null, fr.errors.outOfContract);
  }
  return parsed.data;
}
