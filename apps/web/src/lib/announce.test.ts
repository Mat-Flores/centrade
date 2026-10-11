import { describe, expect, it } from "vitest";

import { announcements, type Snapshot } from "./announce";
import type { Alert, Command, Instance } from "./instances";

const T = "2026-10-11T15:00:00Z";

const inst = (over: Partial<Instance> & { value?: Instance["state"]["value"] } = {}): Instance => {
  const { value = "exits_only", ...rest } = over;
  return {
    id: "i-1",
    name: "alpha",
    engine: "fake",
    desired_mode: "paper",
    desired_state: "exits_only",
    state: { value, observed_at: T, stale: false },
    observed_mode: { value: "paper", observed_at: T, stale: false },
    mode_mismatch: false,
    active_command: null,
    created_at: T,
    server_time: T,
    ...rest,
  };
};
const cmd = (status: Command["status"], over: Partial<Command> = {}): Command => ({
  id: "c-1",
  instance_id: "i-1",
  type: "resume_entries",
  status,
  requested_at: T,
  deadline_at: T,
  server_time: T,
  ...over,
});
const alert = (id: string, over: Partial<Alert> = {}): Alert => ({
  id,
  rule: "r",
  severity: "critical",
  target_kind: "instance",
  status: "open",
  message: "Le mode observé diffère du mode voulu.",
  created_at: T,
  ...over,
});
const snap = (over: Partial<Snapshot> = {}): Snapshot => ({ instances: [inst()], commands: [], alerts: [], degraded: false, ...over });

describe("annonces à l'écran de lecture (WCAG 4.1.3)", () => {
  it("ne dit rien quand rien n'a changé : pas d'annonce à chaque battement", () => {
    expect(announcements(snap(), snap())).toEqual([]);
    expect(announcements(snap(), snap({ instances: [inst({ server_time: "2026-10-11T15:00:05Z" })] }))).toEqual([]);
  });

  it("annonce le changement d'état observé d'une instance", () => {
    expect(announcements(snap(), snap({ instances: [inst({ value: "running" })] }))).toEqual(["alpha : état observé en marche."]);
    expect(announcements(snap(), snap({ instances: [inst({ value: "unknown" })] }))).toEqual(["alpha : état observé inconnu."]);
  });

  it("annonce l'étape terminale d'une commande, pas les étapes en cours", () => {
    const base = snap({ commands: [cmd("requested")] });
    expect(announcements(base, snap({ commands: [cmd("acknowledged")] }))).toEqual([]);
    expect(announcements(base, snap({ commands: [cmd("verified")] }))).toEqual([
      "Réouverture des entrées sur alpha : faite, effet observé dans le moteur.",
    ]);
    expect(announcements(base, snap({ commands: [cmd("timed_out")] }))[0]).toContain("délai dépassé : effet non observé");
    expect(announcements(base, snap({ commands: [cmd("failed")] }))[0]).toContain("en échec");
  });

  it("n'annonce pas deux fois une commande déjà terminale", () => {
    expect(announcements(snap({ commands: [cmd("verified")] }), snap({ commands: [cmd("verified")] }))).toEqual([]);
  });

  it("annonce une nouvelle alerte ouverte, pas les anciennes", () => {
    const before = snap({ alerts: [alert("a1")] });
    expect(announcements(before, snap({ alerts: [alert("a1")] }))).toEqual([]);
    expect(announcements(before, snap({ alerts: [alert("a2", { message: "Le moteur ne répond plus." }), alert("a1")] }))).toEqual([
      "Nouvelle alerte critique : Le moteur ne répond plus.",
    ]);
  });

  it("annonce l'entrée et la sortie du mode dégradé", () => {
    expect(announcements(snap(), snap({ degraded: true }))[0]).toMatch(/^Mode dégradé/);
    expect(announcements(snap({ degraded: true }), snap())[0]).toMatch(/^Fin du mode dégradé/);
  });
});
