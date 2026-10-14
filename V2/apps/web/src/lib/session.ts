import { QueryClient, queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { ApiError, apiFetch, setUnauthorizedHandler } from "./api";

export const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });

export const MeSchema = z.object({ email: z.string(), role: z.enum(["viewer", "operator", "admin"]) });
export type Me = z.infer<typeof MeSchema>;

export const meKey = ["auth", "me"] as const;

/** `null`: no session (401). Any other failure stays an error: a missing session is never guessed. */
export async function fetchMe(signal?: AbortSignal): Promise<Me | null> {
  try {
    return await apiFetch("/auth/me", MeSchema, { signal, authCall: true });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export const meQuery = queryOptions({ queryKey: meKey, queryFn: ({ signal }) => fetchMe(signal), staleTime: 60_000 });

/** Session over (logout or 401): nothing of the previous account stays in the cache. */
export function endSession(): void {
  // `me` stays in the cache (mounted observers follow it); everything else of the previous account goes.
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== meKey[0] || query.queryKey[1] !== meKey[1] });
  queryClient.setQueryData(meKey, null);
}

setUnauthorizedHandler(endSession);

export const logout = () => apiFetch("/auth/logout", z.unknown(), { method: "POST" });
