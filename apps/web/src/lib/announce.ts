import { useEffect, useRef, useState } from "react";

import { fr } from "@/i18n/fr";
import type { Alert, Command, Instance } from "@/lib/instances";

export interface Snapshot {
  instances: Instance[];
  commands: Command[];
  alerts: Alert[];
  degraded: boolean;
}

const TERMINAL = new Set<Command["status"]>(["verified", "failed", "timed_out", "superseded"]);

/**
 * Ce qui mérite d'être dit à voix haute entre deux relevés (WCAG 4.1.3) : un changement d'état observé,
 * l'étape terminale d'une commande, une nouvelle alerte, l'entrée ou la sortie du mode dégradé.
 * Rien d'autre : ni battement, ni étape intermédiaire, ni âge qui avance.
 */
export function announcements(prev: Snapshot, next: Snapshot): string[] {
  const out: string[] = [];
  const a = fr.announce;
  const before = new Map(prev.instances.map((i) => [i.id, i]));
  const names = new Map(next.instances.map((i) => [i.id, i.name]));

  for (const i of next.instances) {
    const old = before.get(i.id);
    if (old && old.state.value !== i.state.value) {
      out.push(a.state(i.name, i.state.value === "unknown" ? fr.observed.unknown : fr.cockpit.states[i.state.value]));
    }
  }

  const oldCommands = new Map(prev.commands.map((c) => [c.id, c]));
  for (const c of next.commands) {
    const old = oldCommands.get(c.id);
    if (!TERMINAL.has(c.status) || old?.status === c.status) continue;
    // Une commande déjà connue comme terminale n'est pas rejouée ; une commande inconnue, déjà finie, l'est.
    if (old && TERMINAL.has(old.status)) continue;
    const type = fr.cockpit.command.types[c.type] ?? c.type;
    out.push(a.command(type, names.get(c.instance_id) ?? "", fr.cockpit.command.status[c.status]));
  }

  const knownAlerts = new Set(prev.alerts.map((x) => x.id));
  for (const al of next.alerts) {
    if (!knownAlerts.has(al.id)) out.push(a.alert(fr.cockpit.alerts.severity[al.severity] ?? al.severity, al.message));
  }

  if (!prev.degraded && next.degraded) out.push(a.degradedOn);
  if (prev.degraded && !next.degraded) out.push(a.degradedOff);
  return out;
}

/** Texte de la région `aria-live` : change seulement quand `announcements` a quelque chose à dire. */
export function useAnnouncement(next: Snapshot, loaded: boolean): string {
  const [message, setMessage] = useState("");
  const prev = useRef<Snapshot | null>(null);
  const { instances, commands, alerts, degraded } = next;
  useEffect(() => {
    if (!loaded) return;
    const current = { instances, commands, alerts, degraded };
    // Premier relevé complet : c'est l'état de départ, pas un changement.
    if (prev.current) {
      const said = announcements(prev.current, current);
      if (said.length > 0) setMessage(said.join(" "));
    }
    prev.current = current;
  }, [instances, commands, alerts, degraded, loaded]);
  return message;
}
