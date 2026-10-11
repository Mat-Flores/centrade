import type { LoginFailure } from "@/lib/login";

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
    opening: "Ouverture de la session…",
  },
  totp: {
    title: "Vérification en deux étapes",
    help: "Saisir le code à 6 chiffres de l'application d'authentification, ou un code de récupération.",
    code: "Code",
    submit: "Valider le code",
    pending: "Vérification en cours…",
    errorTitle: "Code non validé",
    back: "Revenir au mot de passe",
  },
  session: {
    checking: "Vérification de la session…",
    errorTitle: "Session impossible à vérifier",
    error: "L'API est injoignable ou a répondu hors contrat. Vérifier la connexion VPN et que l'API est démarrée, puis réessayer.",
    retry: "Réessayer",
  },
  roles: { viewer: "lecteur", operator: "opérateur", admin: "administrateur" },
  bar: {
    label: "Barre d'état",
    mode: "Mode",
    modes: { paper: "PAPER", live: "LIVE", unknown: "inconnu" },
    connections: "Connexions",
    connectionNames: { engines: "Moteurs", bus: "Bus", database: "Base" },
    health: { ok: "en service", degraded: "dégradé", down: "hors service", unknown: "inconnu" },
    alerts: "Alertes",
    alertsUnknown: "inconnu",
    killSwitch: "Kill switch global",
    killSwitchReason: "Disponible au jalon M3",
    theme: { toDark: "Passer au thème sombre", toLight: "Passer au thème clair" },
    logout: "Se déconnecter",
    loggingOut: "Déconnexion…",
    logoutFailedTitle: "Déconnexion non confirmée",
    logoutFailed: "L'API n'a pas confirmé la fermeture de la session. Réessayer.",
  },
  nav: {
    label: "Écrans",
    comingSoon: "à venir",
    items: {
      cockpit: "Cockpit",
      strategies: "Stratégies",
      orders: "Ordres et positions",
      risk: "Risque",
      accounts: "Comptes et clés",
      flow: "Flow",
      agents: "Agents",
      signals: "Signaux et backtests",
      journal: "Journal et rapports",
      settings: "Paramètres",
    },
  },
  cockpit: {
    title: "Cockpit",
    emptyTitle: "Aucune instance à afficher",
    emptyBody: "Les instances et leur état observé apparaîtront ici dès que le Cockpit sera branché sur l'API.",
  },
  observed: {
    unknown: "inconnu",
    unknownHint: "Aucune valeur observée : l'état réel n'est pas connu.",
    observedAt: "Observé",
    staleSince: (age: string) => `périmé depuis ${age.replace(/^il y a /, "")}`,
  },
  footer: "Ce logiciel n'est pas un conseil financier.",
};

/** Cause connue + action possible (PRODUCT.md : ton neutre, à l'infinitif). */
export function loginErrorMessage(failure: LoginFailure, step: "password" | "totp"): string {
  switch (failure.cause) {
    case "refused":
      return step === "password"
        ? "Identifiant ou mot de passe refusé. Vérifier la saisie, puis réessayer."
        : "Code refusé, ou connexion expirée. Vérifier le code, puis réessayer ; au besoin, revenir au mot de passe.";
    case "locked":
      return "Compte verrouillé après des échecs répétés. Patienter avant de réessayer ; au besoin, demander à un administrateur de le déverrouiller.";
    case "rate-limited":
      return "Trop de tentatives. Patienter quelques minutes, puis réessayer.";
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
