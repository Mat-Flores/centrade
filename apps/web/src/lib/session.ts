import { QueryClient, queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { ApiError, apiFetch, setUnauthorizedHandler } from "./api";

export const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });

export const MeSchema = z.object({ email: z.string(), role: z.enum(["viewer", "operator", "admin"]) });
export type Me = z.infer<typeof MeSchema>;

export const meKey = ["auth", "me"] as const;

/** `null` : aucune session (401). Toute autre panne reste une erreur : on ne devine pas l'absence de session. */
export async function fetchMe(signal?: AbortSignal): Promise<Me | null> {
  try {
    return await apiFetch("/auth/me", MeSchema, { signal, authCall: true });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export const meQuery = queryOptions({ queryKey: meKey, queryFn: ({ signal }) => fetchMe(signal), staleTime: 60_000 });

/** Session finie (déconnexion ou 401) : plus rien du compte précédent ne reste en cache. */
export function endSession(): void {
  // `me` reste dans le cache (les observateurs montés le suivent) ; tout le reste du compte précédent part.
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== meKey[0] || query.queryKey[1] !== meKey[1] });
  queryClient.setQueryData(meKey, null);
}

setUnauthorizedHandler(endSession);

export const logout = () => apiFetch("/auth/logout", z.unknown(), { method: "POST" });
