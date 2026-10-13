import { useState } from "react";
import { STALE_AFTER } from "../../app/common";
import { Button } from "../../ui/ui";
import { signedMoney } from "../../lib/format";
import type { Instance, ObservedState, WantedState } from "../../data/types";

export type Face = "observation" | "reglages";

export const STATE_LABEL: Record<ObservedState, string> = {
  arrete: "Arrêté", lancement: "Lancement", verification: "Vérification", actif: "Actif",
  achats_en_pause: "Achats en pause", erreur: "Erreur", inconnu: "Inconnu",
};
export const WANTED_LABEL: Record<WantedState, string> = { arrete: "Arrêté", actif: "Actif", achats_en_pause: "Achats en pause" };

export const isLive = (i: Instance): boolean => i.mode !== "backtest";
/** Un bot arrêté n'a rien à rapporter : seul un bot censé tourner peut être périmé. */
export const isStale = (i: Instance, cursor: number): boolean => isLive(i) && i.observed !== "arrete" && cursor - i.observedAt > STALE_AFTER;

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
