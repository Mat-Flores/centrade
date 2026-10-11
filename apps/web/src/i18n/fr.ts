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
    skip: "Aller au contenu",
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
    instances: "Instances",
    simulated: "simulé",
    simulatedHint: "Instance paper : aucun ordre réel, chiffres simulés.",
    modeUnknown: "mode inconnu",
    modeMismatch: "MODE INCOHÉRENT",
    modeMismatchDetail: (wanted: string, observed: string) => `voulu ${wanted}, observé ${observed}`,
    observedState: "État observé",
    wantedState: "État voulu",
    wantedLabels: { running: "en marche", exits_only: "sorties seules", stopped: "arrêté" },
    states: {
      starting: "démarrage",
      exits_only: "sorties seules",
      running: "en marche",
      halted: "boucle arrêtée",
      stopped: "arrêté",
      error: "erreur",
    },
    summary: {
      label: "Instances par état observé",
      total: (n: number) => `${n} ${n > 1 ? "instances" : "instance"}`,
      stale: "périmé",
      unknown: "inconnu",
    },
    loading: "Chargement des instances…",
    loadError: {
      title: "Instances indisponibles",
      body: "L'API n'a pas renvoyé la liste des instances. Vérifier que l'API est démarrée et la connexion VPN, puis réessayer.",
      retry: "Réessayer",
    },
    empty: {
      title: "Aucune instance",
      body: "Une instance simulée ne passe aucun ordre réel. Créer la première pour voir son état observé en temps réel.",
      bodyViewer: "Aucune instance n'existe encore. Un opérateur peut en créer une.",
    },
    create: {
      open: "Créer une instance simulée",
      name: "Nom de l'instance",
      help: "Lettres, chiffres, point, tiret et souligné ; 64 caractères au plus. L'instance est simulée (paper) et démarre en sorties seules.",
      submit: "Créer l'instance",
      pending: "Création en cours…",
      cancel: "Annuler",
      invalid: "Nom invalide : commencer par une lettre ou un chiffre, puis lettres, chiffres, « . », « - » ou « _ ».",
      errorTitle: "Création impossible",
      conflict: "Une instance porte déjà ce nom. Choisir un autre nom.",
      error: "L'API a refusé la création. Vérifier le nom et que l'API est démarrée, puis réessayer.",
    },
    actions: {
      label: (name: string) => `Actions sur ${name}`,
      pause_entries: "Bloquer les entrées",
      resume_entries: "Rouvrir les entrées",
      flatten: "Tout fermer",
      stop: "Arrêter",
      start: "Démarrer",
    },
    reasons: {
      degraded: "Mode dégradé : seules les actions qui réduisent le risque restent possibles.",
      unknown: "L'état observé est inconnu.",
      stale: "L'état observé est périmé.",
      alreadyOpen: "Les entrées sont déjà ouvertes.",
      alreadyStarted: "L'instance est déjà démarrée.",
      modeMismatch: "Le mode observé diffère du mode voulu.",
      adminOnly: "Réservé aux administrateurs : le mode voulu de l'instance n'est pas paper.",
      notExitsOnly: (state: string) => `État observé « ${state} » : reprise impossible.`,
      unavailable: (action: string, why: string) => `${action} indisponible : ${why}`,
    },
    confirm: {
      cancel: "Annuler",
      pending: "Envoi en cours…",
      title: (action: string, name: string) => `${action} : ${name}`,
      observedNow: (state: string, age: string) => `État observé à cet instant : ${state} (${age}).`,
      observedStale: (state: string, since: string) =>
        `État observé périmé depuis ${since} (dernier relevé : ${state}). L'effet réel peut différer de ce qui est annoncé.`,
      observedUnknown: "État observé inconnu : la conséquence réelle ne peut pas être annoncée.",
      errorTitle: "Commande refusée",
      errorFallback: "L'API n'a pas accepté la commande. Réessayer ; si cela persiste, vérifier que l'API est démarrée.",
      consequences: {
        pause_entries:
          "Plus aucune nouvelle entrée ne sera ouverte ; les positions ouvertes et leurs sorties restent gérées. Réduit le risque, sans délai.",
        resume_entries:
          "Les entrées seront rouvertes : le moteur pourra ouvrir de nouvelles positions. Augmente le risque ; refusé si l'état observé est inconnu ou périmé.",
        flatten:
          "Toutes les positions de l'instance seront fermées. Le nombre de positions ouvertes n'est pas encore relevé : la commande vise toutes les positions. Réduit le risque, sans délai.",
        stop: "L'instance cesse d'ouvrir des entrées puis s'arrête. Pour fermer d'abord les positions, utiliser « Tout fermer ».",
        start: "L'instance démarre toujours en sorties seules ; les entrées ne s'ouvrent qu'avec « Rouvrir les entrées », après vérification.",
      },
    },
    command: {
      types: {
        deploy: "Déploiement",
        start: "Démarrage",
        stop: "Arrêt",
        pause_entries: "Blocage des entrées",
        resume_entries: "Réouverture des entrées",
        flatten: "Fermeture de tout",
      } as Record<string, string>,
      status: {
        requested: "demandée, pas encore transmise au moteur",
        dispatched: "transmise au moteur, pas encore reçue",
        acknowledged: "reçue par le moteur, effet pas encore observé",
        verified: "faite, effet observé dans le moteur",
        failed: "en échec",
        timed_out: "délai dépassé : effet non observé",
        superseded: "remplacée par une commande plus urgente",
      },
      noReason: "Aucune raison fournie par le moteur.",
      reason: "Raison",
      seen: "Marquer comme vu",
      problemTitle: "Commande à vérifier",
    },
    alerts: {
      title: "Alertes ouvertes",
      none: "Aucune alerte ouverte.",
      loading: "Chargement des alertes…",
      error: "Alertes indisponibles. Vérifier que l'API est démarrée, puis recharger la page.",
      severity: { info: "info", warning: "avertissement", critical: "critique" } as Record<string, string>,
      target: { instance: "instance", account: "compte", global: "global" } as Record<string, string>,
      columns: { severity: "Gravité", target: "Cible", message: "Message", age: "Âge" },
    },
    health: {
      title: "Santé des services",
      names: { database: "Base de données", bus: "Bus", worker: "Worker" } as Record<string, string>,
      ok: "en service",
      down: "hors service",
      unknown: "inconnu",
      observedAt: (when: string) => `relevé ${when}`,
      error: "Santé introuvable : l'API ne répond pas.",
      loading: "Relevé de la santé…",
    },
    degraded: {
      title: "Mode dégradé",
      stream: "Le flux temps réel est coupé : les données affichées peuvent être périmées.",
      health: "Un service du noyau est en panne.",
      healthUnknown: "La santé des services est introuvable.",
      rule: "Seules les actions qui réduisent le risque restent actives.",
    },
  },
  announce: {
    state: (name: string, state: string) => `${name} : état observé ${state}.`,
    command: (type: string, name: string, status: string) => `${type} sur ${name} : ${status}.`,
    alert: (severity: string, message: string) => `Nouvelle alerte ${severity} : ${message}`,
    degradedOn: "Mode dégradé : seules les actions qui réduisent le risque restent actives.",
    degradedOff: "Fin du mode dégradé : les données sont de nouveau à jour.",
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
        ? "Identifiant ou mot de passe refusé, ou compte temporairement verrouillé. Vérifier la saisie, puis réessayer ; après des échecs répétés, patienter avant un nouvel essai."
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
