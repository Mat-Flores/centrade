export type LoginResult =
  | { ok: true }
  | { ok: false; cause: "refused" | "rate-limited" | "network" | "unexpected" }
  | { ok: false; cause: "http"; status: number };

export const LOGIN_URL = "/api/v1/auth/login";

/**
 * Envoie les identifiants. Un succès n'est déclaré que si l'API répond 2xx
 * (204, ou JSON) : une 2xx d'une autre nature (repli HTML d'un serveur de
 * fichiers) n'est pas une réponse de l'API. Le mot de passe n'est ni retenu ni
 * renvoyé dans le résultat.
 */
export async function submitLogin(
  credentials: { username: string; password: string },
  fetchImpl: typeof fetch = fetch,
): Promise<LoginResult> {
  let response: Response;
  try {
    response = await fetchImpl(LOGIN_URL, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(credentials),
      credentials: "same-origin",
    });
  } catch {
    return { ok: false, cause: "network" };
  }
  const { status } = response;
  if (status >= 200 && status < 300) {
    const isJson = response.headers.get("content-type")?.includes("application/json") ?? false;
    return status === 204 || isJson ? { ok: true } : { ok: false, cause: "unexpected" };
  }
  if (status === 401 || status === 403) return { ok: false, cause: "refused" };
  if (status === 429) return { ok: false, cause: "rate-limited" };
  return { ok: false, cause: "http", status };
}
