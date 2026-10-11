import { z } from "zod";

/** Seul point d'accès réseau du front : même origine, aucune URL tierce (CSP `connect-src 'self'`). */
export const API_BASE = "/api/v1";

const ProblemSchema = z.object({
  type: z.string().optional(),
  title: z.string().optional(),
  status: z.number().optional(),
  detail: z.string().optional(),
});
export type Problem = z.infer<typeof ProblemSchema>;

export type ApiErrorKind = "network" | "problem" | "invalid-response";

/** Erreur unique de l'API : réseau coupé, problème RFC 7807 (ou erreur HTTP brute) ou réponse hors contrat. */
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

/** Appelé sur tout 401 (sauf appels d'authentification) : la session n'existe plus, retour au login. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

export interface ApiRequest {
  method?: "GET" | "POST" | "PUT";
  body?: unknown;
  /** En-têtes en plus des défauts (ex. `Idempotency-Key` d'une commande). */
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** Les appels d'authentification lisent eux-mêmes le 401 (identifiants refusés) : pas de retour au login. */
  authCall?: boolean;
  fetchImpl?: typeof fetch;
}

async function readProblem(response: Response): Promise<Problem | null> {
  if (!(response.headers.get("content-type") ?? "").includes("json")) return null;
  try {
    const parsed = ProblemSchema.safeParse(await response.json());
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

/** Appelle `/api/v1{path}` et ne renvoie que des données conformes au schéma Zod. */
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
    if (signal?.aborted) throw cause; // annulation voulue (TanStack Query), pas une panne
    throw new ApiError("network", null, null, "API injoignable");
  }

  if (!response.ok) {
    if (response.status === 401 && !authCall) onUnauthorized?.();
    const problem = await readProblem(response);
    throw new ApiError(
      "problem",
      response.status,
      problem,
      problem?.title ?? problem?.detail ?? `Erreur HTTP ${response.status}`,
    );
  }

  let data: unknown;
  if (response.status !== 204) {
    // Une 2xx qui n'est pas du JSON (repli HTML d'un serveur de fichiers) n'est pas une réponse de l'API.
    if (!(response.headers.get("content-type") ?? "").includes("application/json")) {
      throw new ApiError("invalid-response", response.status, null, "Réponse inattendue : ce n'est pas du JSON");
    }
    try {
      data = await response.json();
    } catch {
      throw new ApiError("invalid-response", response.status, null, "Réponse JSON illisible");
    }
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    throw new ApiError("invalid-response", response.status, null, "Réponse hors contrat");
  }
  return parsed.data;
}
