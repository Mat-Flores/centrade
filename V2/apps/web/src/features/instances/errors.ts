import { fr } from "@/i18n/fr";
import { ApiError } from "@/lib/api";

/** What the operator reads about a refused request: the server's detail when it gave one, else a plain cause. */
export function refusal(error: unknown, fallback: string): { text: string; reasons: string[] } {
  if (error instanceof ApiError) {
    if (error.kind === "network") return { text: fr.instances.create.errorNetwork, reasons: [] };
    if (error.kind === "problem") return { text: error.problem?.detail ?? error.problem?.title ?? fallback, reasons: error.problem?.reasons ?? [] };
  }
  return { text: fallback, reasons: [] };
}
