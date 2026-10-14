import { describe, expect, it } from "vitest";

import { announcements, type Snapshot } from "./announce";
import type { Alert, Command, Instance } from "./instances";
import { makeAlert, makeCommand, makeInstance } from "@/test/factories";

const T = "2026-10-11T15:00:00Z";

const inst = (over: Partial<Instance> & { value?: Instance["state"]["value"] } = {}): Instance => {
  const { value = "exits_only", ...rest } = over;
  return makeInstance({
    desired_state: "exits_only",
    state: { value, observed_at: T, stale: false },
    observed_mode: { value: "paper", observed_at: T, stale: false },
    created_at: T,
    server_time: T,
    ...rest,
  });
};
const cmd = (status: Command["status"], over: Partial<Command> = {}): Command =>
  makeCommand({ status, requested_at: T, deadline_at: T, server_time: T, ...over });
const alert = (id: string, over: Partial<Alert> = {}): Alert => makeAlert(id, { created_at: T, ...over });
const snap = (over: Partial<Snapshot> = {}): Snapshot => ({ instances: [inst()], commands: [], alerts: [], degraded: false, ...over });

describe("screen-reader announcements (WCAG 4.1.3)", () => {
  it("says nothing when nothing changed: no announcement on every heartbeat", () => {
    expect(announcements(snap(), snap())).toEqual([]);
    expect(announcements(snap(), snap({ instances: [inst({ server_time: "2026-10-11T15:00:05Z" })] }))).toEqual([]);
  });

  it("announces an observed state change of an instance", () => {
    expect(announcements(snap(), snap({ instances: [inst({ value: "running" })] }))).toEqual(["alpha : état observé en marche."]);
    expect(announcements(snap(), snap({ instances: [inst({ value: "unknown" })] }))).toEqual(["alpha : état observé inconnu."]);
  });

  it("announces the terminal stage of a command, not the intermediate ones", () => {
    const base = snap({ commands: [cmd("requested")] });
    expect(announcements(base, snap({ commands: [cmd("acknowledged")] }))).toEqual([]);
    expect(announcements(base, snap({ commands: [cmd("verified")] }))).toEqual([
      "Réouverture des entrées sur alpha : faite, effet observé dans le moteur.",
    ]);
    expect(announcements(base, snap({ commands: [cmd("timed_out")] }))[0]).toContain("délai dépassé : effet non observé");
    expect(announcements(base, snap({ commands: [cmd("failed")] }))[0]).toContain("en échec");
  });

  it("does not announce an already terminal command twice", () => {
    expect(announcements(snap({ commands: [cmd("verified")] }), snap({ commands: [cmd("verified")] }))).toEqual([]);
  });

  it("announces a new open alert, not the old ones", () => {
    const before = snap({ alerts: [alert("a1")] });
    expect(announcements(before, snap({ alerts: [alert("a1")] }))).toEqual([]);
    expect(announcements(before, snap({ alerts: [alert("a2", { message: "The engine no longer answers." }), alert("a1")] }))).toEqual([
      "Nouvelle alerte critique : The engine no longer answers.",
    ]);
  });

  it("announces entering and leaving degraded mode", () => {
    expect(announcements(snap(), snap({ degraded: true }))[0]).toMatch(/^Mode dégradé/);
    expect(announcements(snap({ degraded: true }), snap())[0]).toMatch(/^Fin du mode dégradé/);
  });
});
