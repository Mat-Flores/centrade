// User-facing texts (French). Code and comments stay in English; no French string lives outside this file.
export const fr = {
  productName: "Centrade",
  errors: {
    apiUnreachable: "API injoignable",
    notJson: "Réponse inattendue : ce n'est pas du JSON",
    unreadableJson: "Réponse JSON illisible",
    outOfContract: "Réponse hors contrat",
    http: (status: number) => `Erreur HTTP ${status}`,
    invalidDecimal: (amount: string) => `Montant décimal invalide : ${amount}`,
    currencyRequired: "La devise est obligatoire",
  },
  age: {
    instant: "à l'instant",
    seconds: (s: number) => `il y a ${s} s`,
    minutes: (min: number) => `il y a ${min} min`,
    hours: (h: number, min: string) => `il y a ${h} h ${min} min`,
    days: (d: number, h: number) => `il y a ${d} j ${h} h`,
  },
  duration: {
    seconds: (s: number) => `${s} s`,
    days: (d: number) => `${d} j`,
    hours: (h: number) => `${h} h`,
    minutes: (m: number) => `${m} min`,
  },
  timeframes: { "5m": "5 min", "15m": "15 min", "1h": "1 h", "4h": "4 h", "1d": "1 j" },
} as const;
