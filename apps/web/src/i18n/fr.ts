import type { LoginResult } from "@/lib/login";

type LoginFailure = Exclude<LoginResult, { ok: true }>;

export const fr = {
  productName: "Centrade",
  login: {
    title: "Connexion",
    access: "Accès réservé à l'opérateur, par VPN.",
    username: "Identifiant",
    password: "Mot de passe",
    submit: "Se connecter",
    pending: "Connexion en cours…",
    errorTitle: "Connexion impossible",
    successTitle: "Connexion acceptée",
    success: "L'API a accepté les identifiants.",
  },
  footer: "Ce logiciel n'est pas un conseil financier.",
};

/** Cause connue + action possible (PRODUCT.md : ton neutre, à l'infinitif). */
export function loginErrorMessage(failure: LoginFailure): string {
  switch (failure.cause) {
    case "refused":
      return "Identifiant ou mot de passe refusé. Vérifier la saisie, puis réessayer.";
    case "rate-limited":
      return "Trop de tentatives de connexion. Patienter quelques minutes, puis réessayer.";
    case "network":
      return "L'API est injoignable. Vérifier la connexion VPN et que l'API est démarrée, puis réessayer.";
    case "unexpected":
      return "La réponse reçue n'est pas celle de l'API de connexion. Vérifier la configuration du serveur frontal, puis réessayer.";
    case "http":
      return failure.status === 404
        ? "Le service de connexion est introuvable (HTTP 404). Vérifier que l'API est démarrée et à jour, puis réessayer."
        : `L'API a répondu par une erreur (HTTP ${failure.status}). Vérifier qu'elle est démarrée, puis réessayer.`;
  }
}
