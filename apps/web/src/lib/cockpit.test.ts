import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import {
  actionPolicy,
  applyStreamMessage,
  countByState,
  currentCommand,
  degradation,
  deriveEngines,
  deriveMode,
  shownMode,
  describeCommand,
  stateView,
  unseenProblems,
  upsertCommand,
  wantedDiffers,
} from "./cockpit";
import { alertsKey, commandsKey, instancesKey, type Alert, type Command, type Instance, type Page } from "./instances";

const NOW = Date.parse("2026-10-11T15:00:00Z");
const iso = (secondsAgo: number) => new Date(NOW - secondsAgo * 1000).toISOString();

function instance(over: Partial<Instance> & { stateValue?: Instance["state"]["value"]; age?: number | null } = {}): Instance {
  const { stateValue = "running", age = 2, ...rest } = over;
  const observedAt = age === null ? null : iso(age);
  return {
    id: "i-1",
    name: "alpha",
    engine: "fake",
    desired_mode: "paper",
    desired_state: "running",
    state: { value: age === null ? "unknown" : stateValue, observed_at: observedAt, stale: false },
    observed_mode: { value: age === null ? "unknown" : "paper", observed_at: observedAt, stale: false },
    mode_mismatch: false,
    active_command: null,
    created_at: iso(3600),
    server_time: iso(0),
    ...rest,
  };
}

function command(over: Partial<Command> = {}): Command {
  return {
    id: "c-1",
    instance_id: "i-1",
    type: "resume_entries",
    status: "requested",
    requested_at: iso(10),
    deadline_at: iso(-20),
    server_time: iso(0),
    ...over,
  };
}

describe("describeCommand : jamais « fait » avant verified (I8)", () => {
  it.each(["requested", "dispatched", "acknowledged"] as const)("%s reste en cours", (status) => {
    expect(describeCommand(command({ status }), NOW).tone).toBe("pending");
  });

  it("verified est la seule commande faite", () => {
    expect(describeCommand(command({ status: "verified", verified_at: iso(1) }), NOW).tone).toBe("done");
  });

  it.each(["failed", "timed_out"] as const)("%s est un problème avec sa raison", (status) => {
    const view = describeCommand(command({ status, result: { reason: "moteur muet" } }), NOW);
    expect(view).toMatchObject({ tone: "problem", reason: "moteur muet" });
  });

  it("un problème sans raison n'invente pas de raison", () => {
    expect(describeCommand(command({ status: "timed_out", result: null }), NOW)).toMatchObject({ reason: null });
  });

  it("l'ancienneté se compte depuis la demande", () => {
    expect(describeCommand(command({ requested_at: iso(42) }), NOW).ageMs).toBe(42_000);
  });
});

describe("commandes : version la plus avancée, échecs non vus", () => {
  it("une version plus ancienne ne remplace pas une plus récente", () => {
    const verified = command({ status: "verified", verified_at: iso(1), dispatched_at: iso(8), acknowledged_at: iso(5) });
    const older = command({ status: "acknowledged", dispatched_at: iso(8), acknowledged_at: iso(5) });
    expect(upsertCommand([verified], older)[0]!.status).toBe("verified");
    expect(upsertCommand([older], verified)[0]!.status).toBe("verified");
  });

  it("la commande active de l'instance et la liste se complètent", () => {
    const fromList = command({ status: "dispatched", dispatched_at: iso(8) });
    const active = command({ status: "acknowledged", dispatched_at: iso(8), acknowledged_at: iso(4) });
    expect(currentCommand(instance({ active_command: active }), [fromList])?.status).toBe("acknowledged");
  });

  it("échec et expiration restent à signaler jusqu'à ce qu'ils soient vus", () => {
    const list = [command({ id: "a", status: "timed_out" }), command({ id: "b", status: "failed" }), command({ id: "c", status: "verified" })];
    expect(unseenProblems(list, new Set()).map((c) => c.id)).toEqual(["a", "b"]);
    expect(unseenProblems(list, new Set(["a"])).map((c) => c.id)).toEqual(["b"]);
  });
});

describe("état observé", () => {
  it("frais, périmé, inconnu", () => {
    expect(stateView(instance({ age: 3 }), NOW).kind).toBe("fresh");
    expect(stateView(instance({ age: 120 }), NOW).kind).toBe("stale");
    expect(stateView(instance({ age: null }), NOW).kind).toBe("unknown");
  });

  it("l'indicateur périmé du serveur l'emporte sur l'âge calculé", () => {
    const i = instance({ age: 3 });
    i.state.stale = true;
    expect(stateView(i, NOW).kind).toBe("stale");
  });

  it("voulu affiché seulement quand il diffère de l'observé frais", () => {
    expect(wantedDiffers(instance({ age: 2, stateValue: "running", desired_state: "running" }), NOW)).toBe(false);
    expect(wantedDiffers(instance({ age: 2, stateValue: "exits_only", desired_state: "running" }), NOW)).toBe(true);
    expect(wantedDiffers(instance({ age: 200, stateValue: "running", desired_state: "running" }), NOW)).toBe(true);
    expect(wantedDiffers(instance({ age: null }), NOW)).toBe(true);
  });

  it("comptes par état présenté", () => {
    const list = [instance({ id: "1" }), instance({ id: "2", age: 200 }), instance({ id: "3", age: null }), instance({ id: "4", stateValue: "exits_only" })];
    expect(countByState(list, NOW)).toEqual({ running: 1, stale: 1, unknown: 1, exits_only: 1 });
  });
});

describe("mode dégradé : quelles actions restent actives", () => {
  const fresh = instance({ age: 2, stateValue: "exits_only", desired_state: "exits_only" });
  const ctx = (degraded: boolean, i = fresh, role: "operator" | "admin" = "operator") => ({ instance: i, degraded, nowMs: NOW, role });

  it("bloquer, tout fermer et arrêter restent actifs en mode dégradé", () => {
    for (const action of ["pause_entries", "flatten", "stop"] as const) {
      expect(actionPolicy(action, ctx(true)).enabled).toBe(true);
    }
  });

  it("rouvrir et démarrer sont désactivés en mode dégradé, avec la raison", () => {
    for (const action of ["resume_entries", "start"] as const) {
      const p = actionPolicy(action, ctx(true));
      expect(p.enabled).toBe(false);
      expect(p.reason).toMatch(/dégradé/);
    }
  });

  it("rouvrir les entrées hors mode dégradé : permis sur un état frais en sorties seules", () => {
    expect(actionPolicy("resume_entries", ctx(false)).enabled).toBe(true);
  });

  it("rouvrir est refusé au moindre doute : inconnu, périmé, déjà ouvert, mode incohérent", () => {
    expect(actionPolicy("resume_entries", ctx(false, instance({ age: null }))).reason).toMatch(/inconnu/);
    expect(actionPolicy("resume_entries", ctx(false, instance({ age: 200, stateValue: "exits_only" }))).reason).toMatch(/périmé/);
    expect(actionPolicy("resume_entries", ctx(false, instance({ stateValue: "running" }))).enabled).toBe(false);
    expect(actionPolicy("resume_entries", ctx(false, instance({ stateValue: "exits_only", mode_mismatch: true }))).reason).toMatch(/mode/);
  });

  it("toute action désactivée a une raison à montrer", () => {
    const cases = [
      ctx(true),
      ctx(false, instance({ age: null })),
      ctx(false, instance({ age: 200, stateValue: "exits_only" })),
      ctx(false, instance({ stateValue: "running" })),
      ctx(false, instance({ stateValue: "exits_only", mode_mismatch: true })),
      ctx(false, instance({ stateValue: "exits_only", desired_mode: "live" })),
    ];
    for (const c of cases) {
      for (const action of ["resume_entries", "start"] as const) {
        const p = actionPolicy(action, c);
        if (!p.enabled) expect(p.reason, `${action}`).toBeTruthy();
      }
    }
  });

  it("l'opérateur ne rouvre ni ne démarre une instance dont le mode voulu n'est pas paper : administrateur requis", () => {
    const live = instance({ stateValue: "exits_only", desired_mode: "live" });
    const stopped = instance({ stateValue: "stopped", desired_mode: "live" });
    const resume = actionPolicy("resume_entries", ctx(false, live, "operator"));
    expect(resume.enabled).toBe(false);
    expect(resume.reason).toMatch(/administrateur/);
    const start = actionPolicy("start", ctx(false, stopped, "operator"));
    expect(start.enabled).toBe(false);
    expect(start.reason).toMatch(/administrateur/);
    expect(actionPolicy("resume_entries", ctx(false, live, "admin")).enabled).toBe(true);
    expect(actionPolicy("start", ctx(false, stopped, "admin")).enabled).toBe(true);
    expect(actionPolicy("start", ctx(false, instance({ stateValue: "stopped" }), "operator")).enabled).toBe(true);
  });

  it("l'opérateur garde les actions qui réduisent le risque sur une instance live", () => {
    const live = instance({ desired_mode: "live" });
    for (const action of ["pause_entries", "flatten", "stop"] as const) {
      expect(actionPolicy(action, ctx(false, live, "operator")).enabled).toBe(true);
    }
  });

  it("les actions qui réduisent le risque ne sont jamais bloquées par un état douteux", () => {
    const unknown = instance({ age: null });
    for (const action of ["pause_entries", "flatten", "stop"] as const) {
      expect(actionPolicy(action, ctx(false, unknown)).enabled).toBe(true);
    }
  });

  it("5 s sans battement, santé dégradée ou introuvable : dégradé", () => {
    const ok = { status: "ok" as const, ts: iso(0), checks: {} };
    expect(degradation({ streamSilentMs: 4_000, health: ok, healthFailed: false }).degraded).toBe(false);
    expect(degradation({ streamSilentMs: 5_001, health: ok, healthFailed: false }).causes).toEqual(["stream"]);
    expect(degradation({ streamSilentMs: 0, health: { ...ok, status: "degraded" }, healthFailed: false }).causes).toEqual(["health"]);
    expect(degradation({ streamSilentMs: 0, health: undefined, healthFailed: true }).causes).toEqual(["health-unknown"]);
  });
});

describe("barre persistante", () => {
  it("badge de mode d'après les modes observés", () => {
    expect(deriveMode(undefined)).toBe("unknown");
    expect(deriveMode([instance({ age: null })])).toBe("unknown");
    expect(deriveMode([instance()])).toBe("paper");
    const live = instance({ id: "2" });
    live.observed_mode.value = "live";
    expect(deriveMode([instance(), live])).toBe("live");
  });

  it("moteurs d'après les états observés, jamais les états voulus", () => {
    expect(deriveEngines([], NOW)).toBe("unknown");
    expect(deriveEngines([instance()], NOW)).toBe("ok");
    expect(deriveEngines([instance(), instance({ id: "2", age: 200 })], NOW)).toBe("degraded");
    expect(deriveEngines([instance(), instance({ id: "2", stateValue: "error" })], NOW)).toBe("down");
  });
});

describe("flux : application des messages au cache", () => {
  function client() {
    const qc = new QueryClient();
    qc.setQueryData<Page<Instance>>(instancesKey, { items: [instance()], next_cursor: null, server_time: iso(0) });
    qc.setQueryData<Page<Command>>(commandsKey, { items: [], next_cursor: null, server_time: iso(0) });
    qc.setQueryData<Page<Alert>>(alertsKey, { items: [], next_cursor: null, server_time: iso(0) });
    return qc;
  }
  const items = <T,>(qc: QueryClient, key: readonly unknown[]) => qc.getQueryData<Page<T>>(key)!.items;

  it("une instance créée apparaît, une instance connue est remplacée", () => {
    const qc = client();
    const created = instance({ id: "i-2", name: "beta", created_at: iso(1), server_time: iso(0) });
    applyStreamMessage(qc, { event: "instance", server_time: iso(0), instance: created });
    expect(items<Instance>(qc, instancesKey).map((i) => i.name)).toEqual(["beta", "alpha"]);
    const changed = instance({ stateValue: "exits_only", server_time: iso(0) });
    applyStreamMessage(qc, { event: "instance", server_time: iso(0), instance: changed });
    expect(items<Instance>(qc, instancesKey).find((i) => i.id === "i-1")?.state.value).toBe("exits_only");
  });

  it("un message plus ancien que le cache est ignoré", () => {
    const qc = client();
    const stale = instance({ stateValue: "stopped", server_time: iso(60) });
    applyStreamMessage(qc, { event: "instance", server_time: iso(60), instance: stale });
    expect(items<Instance>(qc, instancesKey)[0]!.state.value).toBe("running");
  });

  it("les commandes avancent d'étape en étape jusqu'à verified", () => {
    const qc = client();
    applyStreamMessage(qc, { event: "command", server_time: iso(0), command: command({ status: "requested" }) });
    applyStreamMessage(qc, { event: "command", server_time: iso(0), command: command({ status: "acknowledged", dispatched_at: iso(6), acknowledged_at: iso(4) }) });
    expect(items<Command>(qc, commandsKey)[0]!.status).toBe("acknowledged");
    applyStreamMessage(qc, { event: "command", server_time: iso(0), command: command({ status: "verified", dispatched_at: iso(6), acknowledged_at: iso(4), verified_at: iso(1) }) });
    expect(items<Command>(qc, commandsKey)).toHaveLength(1);
    expect(items<Command>(qc, commandsKey)[0]!.status).toBe("verified");
  });

  it("une alerte résolue quitte la liste des alertes ouvertes", () => {
    const qc = client();
    const alert: Alert = { id: "a-1", rule: "r", severity: "critical", target_kind: "instance", target_id: "i-1", status: "open", message: "m", created_at: iso(5) };
    applyStreamMessage(qc, { event: "alert", server_time: iso(0), alert });
    expect(items<Alert>(qc, alertsKey)).toHaveLength(1);
    applyStreamMessage(qc, { event: "alert", server_time: iso(0), alert: { ...alert, status: "resolved" } });
    expect(items<Alert>(qc, alertsKey)).toHaveLength(0);
  });

  it("une liste pas encore chargée n'est pas inventée", () => {
    const qc = new QueryClient();
    applyStreamMessage(qc, { event: "instance", server_time: iso(0), instance: instance() });
    expect(qc.getQueryData(instancesKey)).toBeUndefined();
  });
});

describe("shownMode : le mode présenté vient du mode observé, jamais du voulu (I1)", () => {
  const nowIso = new Date(NOW).toISOString();
  it("voulu PAPER, observé LIVE frais : live", () => {
    const i = instance({ desired_mode: "paper", mode_mismatch: true, observed_mode: { value: "live", observed_at: iso(2), stale: false } });
    expect(shownMode(i, nowIso)).toBe("live");
  });
  it("observé paper frais : paper", () => expect(shownMode(instance(), nowIso)).toBe("paper"));
  it("observé périmé : inconnu, même si le voulu est paper", () => expect(shownMode(instance({ age: 95 }), nowIso)).toBe("unknown"));
  it("observé inconnu ou instance absente : inconnu", () => {
    expect(shownMode(instance({ age: null }), nowIso)).toBe("unknown");
    expect(shownMode(undefined, nowIso)).toBe("unknown");
  });
});
