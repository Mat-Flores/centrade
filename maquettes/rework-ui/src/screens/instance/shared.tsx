import { useState } from "react";
import { Button } from "../../ui/ui";
import { signedMoney, signedPct } from "../../lib/format";
import type { Instance, ObservedState, WantedState } from "../../data/types";

export type Face = "observation" | "reglages";
/** Au-delà de 60 minutes simulées sans observation, les valeurs du bot sont périmées. */
export const STALE_AFTER_SEC = 3600;

export const STATE_LABEL: Record<ObservedState, string> = {
  arrete: "Arrêté", lancement: "Lancement", verification: "Vérification", actif: "Actif",
  achats_en_pause: "Achats en pause", erreur: "Erreur", inconnu: "Inconnu",
};
export const WANTED_LABEL: Record<WantedState, string> = { arrete: "Arrêté", actif: "Actif", achats_en_pause: "Achats en pause" };

export const isLive = (i: Instance): boolean => i.mode !== "backtest";
/** Un bot arrêté n'a rien à rapporter : seul un bot censé tourner peut être périmé. */
export const isStale = (i: Instance, cursor: number): boolean => isLive(i) && i.observed !== "arrete" && cursor - i.observedAt > STALE_AFTER_SEC;

export function plainPct(n: number, digits = 0): string {
  return `${new Intl.NumberFormat("fr-CA", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n)} %`;
}
export function plainNum(n: number, digits = 2): string {
  return new Intl.NumberFormat("fr-CA", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
}

/** Raison pour laquelle l'instance ne peut pas démarrer, ou null. */
export function startBlock(i: Instance, killSwitch: boolean): string | null {
  if (i.command?.status === "en_cours") return "Une commande est en cours.";
  if (!i.pairs.length) return "Ajouter au moins une paire.";
  if (!i.keyId) return i.mode === "reel" ? "Choisir une clé de production dans les réglages." : "Choisir un compte dans les réglages.";
  if (killSwitch) return "Arrêt d'urgence actif : les achats sont bloqués.";
  return null;
}

export function Arrow({ up }: { up: boolean }) {
  return (
    <svg width="9" height="9" viewBox="0 0 10 10" aria-hidden="true" style={{ flex: "none", transform: up ? undefined : "rotate(180deg)" }}>
      <path d="M5 1.5 9.5 9h-9z" fill="currentColor" />
    </svg>
  );
}

/** Variation en pourcentage : flèche + signe + couleur. « progress » = en cours, toujours en bleu. */
export function Delta({ value, tone }: { value: number; tone: "real" | "progress" }) {
  const zero = Math.round(Math.abs(value) * 100) === 0;
  const cls = tone === "progress" ? "act" : zero ? "dim" : value > 0 ? "up" : "dn";
  return (
    <span className={`num ${cls}`} style={{ display: "inline-flex", alignItems: "center", gap: 4, whiteSpace: "nowrap" }}>
      {!zero && <Arrow up={value > 0} />}
      {signedPct(value)}
    </span>
  );
}

export function Money({ value, currency }: { value: number; currency: string }) {
  const zero = Math.round(Math.abs(value) * 100) === 0;
  return <span className={`num ${zero ? "dim" : value > 0 ? "up" : "dn"}`}>{signedMoney(value, currency)}</span>;
}

/** Exécute une action du store : un refus (Error en français) est gardé pour l'afficher à l'endroit voulu. */
export function useRun(): [string | null, (fn: () => unknown) => void, () => void] {
  const [err, setErr] = useState<string | null>(null);
  const run = (fn: () => unknown) => {
    try { fn(); setErr(null); } catch (e) { setErr(e instanceof Error ? e.message : "Action refusée."); }
  };
  return [err, run, () => setErr(null)];
}

export function ErrorStrip({ message, onClose }: { message: string | null; onClose: () => void }) {
  if (!message) return null;
  return (
    <div className="notice loss in-err" role="alert">
      <span>{message}</span>
      <span className="sp" />
      <Button small variant="ghost" onClick={onClose}>Fermer</Button>
    </div>
  );
}

export const openTradeCount = (trades: { exitTime?: number }[]): number => trades.filter((t) => t.exitTime === undefined).length;
