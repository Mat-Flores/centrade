import { useSyncExternalStore } from "react";
import { INITIAL_CURSOR, newBacktestConfig, seedState } from "./seed";
import { selectTrades } from "./derive";
import { BASE_STEP, EPOCH, PAIRS, SERIES_END, priceAt } from "./sim";
import type { State } from "./state";
import type {
  ApiKey, Automation, BacktestConfig, ColorRoles, Command, CommandStep, Instance, LogEntry, Mode, ObservedState, Strategy, WantedState,
} from "./types";

export type { State } from "./state";
export { INITIAL_CURSOR } from "./seed";
export { CAUSE_LABEL, selectCandles, selectLog, selectStats, selectTrades } from "./derive";

const REEL_MSG = "Une instance en mode réel ne se modifie pas : modifier l'instance de test, puis repasser en réel.";

// ---------- noyau : état immuable, abonnés, minuteries annulables ----------

let state: State = seedState();
let counter = 0;
const listeners = new Set<() => void>();
const intervals = new Set<ReturnType<typeof setInterval>>();
const timeouts = new Set<ReturnType<typeof setTimeout>>();
const playStops = new Map<string, () => void>();
let stopClockFn: (() => void) | null = null;

export const getState = (): State => state;
export function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}
export function useStore<T>(selector: (s: State) => T): T {
  return useSyncExternalStore(subscribe, () => selector(state));
}

function set(fn: (s: State) => State): void {
  const next = fn(state);
  if (next === state) return;
  state = next;
  listeners.forEach((l) => l());
}

const uid = (prefix: string): string => `${prefix}-${++counter}`;

function later(ms: number, fn: () => void): void {
  const id = setTimeout(() => { timeouts.delete(id); fn(); }, ms);
  timeouts.add(id);
}

function every(ms: number, fn: () => void): () => void {
  const id = setInterval(fn, ms);
  intervals.add(id);
  return () => { clearInterval(id); intervals.delete(id); };
}

/** Progression 0 à 100 en `ms`, par pas de 100 ms. */
function animate(ms: number, onProgress: (p: number) => void, onDone: () => void): void {
  const steps = Math.max(1, Math.round(ms / 100));
  let i = 0;
  const stop = every(100, () => {
    i++;
    onProgress(Math.round((i * 100) / steps));
    if (i >= steps) { stop(); onDone(); }
  });
}

export function startClock(): void {
  stopClockFn ??= every(1500, tick);
}
export function stopClock(): void {
  stopClockFn?.();
  stopClockFn = null;
}

export function resetStore(): void {
  stopClock();
  intervals.forEach(clearInterval);
  timeouts.forEach(clearTimeout);
  intervals.clear();
  timeouts.clear();
  playStops.clear();
  counter = 0;
  state = seedState();
  listeners.forEach((l) => l());
}

function tick(): void {
  set((s) => {
    const cursor = Math.min(s.cursor + BASE_STEP, SERIES_END);
    if (cursor === s.cursor) return s;
    // Données figées : le temps passe mais le bot ne rapporte plus rien, donc `observedAt` vieillit.
    const instances = s.demo.frozen ? s.instances : s.instances.map((i) => (i.observed === "arrete" ? i : { ...i, observedAt: cursor }));
    return { ...s, cursor, instances };
  });
}

// ---------- accès et mise à jour d'une instance ----------

function get(id: string): Instance {
  const i = state.instances.find((x) => x.id === id);
  if (!i) throw new Error("Instance introuvable.");
  return i;
}

function patch(id: string, fn: (i: Instance) => Instance): void {
  set((s) => ({ ...s, instances: s.instances.map((i) => (i.id === id ? fn(i) : i)) }));
}

const event = (kind: LogEntry["kind"], text: string): LogEntry => ({ id: uid("ev"), time: state.cursor, kind, text });

function openPause(i: Instance): Instance["entryPauses"] {
  const last = i.entryPauses[i.entryPauses.length - 1];
  return last && last.to === null ? i.entryPauses : [...i.entryPauses, { from: state.cursor, to: null }];
}
function closePause(i: Instance): Instance["entryPauses"] {
  return i.entryPauses.map((p) => (p.to === null ? { ...p, to: state.cursor } : p));
}

/** Constat : l'état observé ne change que par ici, jamais au moment de la demande. */
function observe(i: Instance, observed: ObservedState, extra: Partial<Instance> = {}): Instance {
  return { ...i, observed, observedAt: state.cursor, ...extra };
}

// ---------- commandes ----------

function begin(id: string, kind: Command["kind"], wanted?: WantedState, steps?: Command["steps"]): string {
  const cmd: Command = { id: uid("cmd"), kind, requestedAt: state.cursor, status: "en_cours", steps };
  patch(id, (i) => ({ ...i, wanted: wanted ?? i.wanted, command: cmd }));
  return cmd.id;
}

/** Exécute `fn` après `ms` seulement si la commande n'a pas été remplacée entre-temps. */
function whenCurrent(id: string, cmdId: string, ms: number, fn: (i: Instance) => Instance): void {
  later(ms, () => patch(id, (i) => (i.command?.id === cmdId ? fn(i) : i)));
}

const done = (i: Instance, status: "constatee" | "echouee" = "constatee", error?: string): Command =>
  ({ ...i.command!, status, error });

function setStep(i: Instance, step: CommandStep, status: "attente" | "en_cours" | "ok" | "echec", detail?: string): Command {
  const steps = i.command!.steps!.map((s) => (s.step === step ? { step, status, detail } : s));
  return { ...i.command!, steps };
}

function assertLive(i: Instance): void {
  if (i.mode === "backtest") throw new Error("Un backtest ne se pilote pas comme un bot : importer les données, puis lancer le backtest.");
}

function startChecks(i: Instance): string {
  const version = i.versions[i.versions.length - 1].n;
  return [
    `Mode constaté : ${i.mode === "reel" ? "réel" : "test"}`, "Configuration relue : identique", `Version ${version} chargée`, "Arrêt d'urgence inactif",
  ].join("\n");
}

function start(id: string): void {
  const inst = get(id);
  assertLive(inst);
  if (!inst.pairs.length) throw new Error("Ajouter au moins une paire avant de démarrer.");
  if (!inst.keyId) throw new Error("Choisir un compte avant de démarrer.");
  if (state.killSwitch) throw new Error("L'arrêt d'urgence est actif : les achats sont bloqués.");
  if (inst.observed !== "arrete") throw new Error("Le bot est déjà démarré.");
  const fail = state.demo.failNextStart;
  if (fail) set((s) => ({ ...s, demo: { ...s.demo, failNextStart: false } }));

  const steps = (["lancement", "verification", "actif"] as const).map((step, n) => ({ step, status: n === 0 ? ("en_cours" as const) : ("attente" as const) }));
  const c = begin(id, "demarrer", "actif", steps);
  const startedAt = (i: Instance) => i.startedAt ?? state.cursor;

  whenCurrent(id, c, 250, (i) => observe(i, "lancement"));
  whenCurrent(id, c, 1200, (i) => ({ ...observe(i, "verification"), command: setStep({ ...i, command: setStep(i, "lancement", "ok") }, "verification", "en_cours") }));
  whenCurrent(id, c, 3200, (i) => {
    if (!fail) return { ...i, command: setStep({ ...i, command: setStep(i, "verification", "ok", startChecks(i)) }, "actif", "en_cours") };
    const detail = "Configuration relue : 1 écart (taille des positions)";
    return observe(i, "achats_en_pause", {
      startedAt: startedAt(i), entryPauses: openPause(i), command: done({ ...i, command: setStep(i, "verification", "echec", detail) }, "echouee", detail),
      events: [...i.events, event("alerte", `Démarrage : ${detail}. Le bot tourne, les achats restent fermés.`)],
    });
  });
  if (!fail) {
    whenCurrent(id, c, 4000, (i) => observe(i, "actif", {
      startedAt: startedAt(i), entryPauses: closePause(i), command: done({ ...i, command: setStep(i, "actif", "ok") }),
      events: [...i.events, event("commande", "Démarrage constaté, le bot est actif")],
    }));
  }
}

function requestPause(id: string, text: string): void {
  const c = begin(id, "pause_achats", "achats_en_pause");
  whenCurrent(id, c, 600, (i) => observe(i, "achats_en_pause", {
    startedAt: i.startedAt ?? state.cursor, entryPauses: openPause(i), command: done(i), events: [...i.events, event("commande", text)],
  }));
}

function pauseEntries(id: string): void {
  const inst = get(id);
  assertLive(inst);
  if (inst.observed === "arrete") throw new Error("Le bot est arrêté : il n'y a pas d'achats à mettre en pause.");
  requestPause(id, "Achats en pause constatés, le bot gère encore ses positions");
}

function resumeEntries(id: string): void {
  const inst = get(id);
  assertLive(inst);
  if (inst.observed !== "achats_en_pause") throw new Error("Les achats ne sont pas en pause.");
  if (state.killSwitch) throw new Error("L'arrêt d'urgence est actif : impossible de reprendre les achats.");
  if (state.cursor - inst.observedAt > 3600) throw new Error("La dernière observation du bot date de plus de 60 minutes : état périmé, reprise refusée.");
  const c = begin(id, "reprendre_achats", "actif");
  whenCurrent(id, c, 1500, (i) => observe(i, "actif", {
    entryPauses: closePause(i), command: done(i), events: [...i.events, event("commande", "Reprise des achats constatée")],
  }));
}

/** Positions ouvertes visibles maintenant, avec le patch qui les ferme ou les laisse ouvertes. */
function settlePositions(i: Instance, how: "vendre" | "laisser"): Instance {
  const open = selectTrades({ ...state, instances: state.instances.map((x) => (x.id === i.id ? i : x)) }, i.id).filter((t) => t.exitTime === undefined);
  if (!open.length) return i;
  const manualExits = { ...i.manualExits };
  for (const t of open) manualExits[t.id] = how === "vendre" ? { time: state.cursor, price: priceAt(t.pair, state.cursor) } : null;
  const text = how === "vendre" ? `${open.length} position(s) vendue(s) au prix du marché` : "Positions laissées ouvertes sans bot";
  return { ...i, manualExits, events: [...i.events, event(how === "vendre" ? "commande" : "alerte", text)] };
}

function stop(id: string, opts: { sellAll: boolean }): void {
  const inst = get(id);
  assertLive(inst);
  if (inst.observed === "arrete") throw new Error("Le bot est déjà arrêté.");
  const c = begin(id, "arreter", "arrete");
  whenCurrent(id, c, 600, (i) => observe(i, "achats_en_pause", { entryPauses: openPause(i) }));
  whenCurrent(id, c, 1400, (i) => settlePositions(i, opts.sellAll ? "vendre" : "laisser"));
  whenCurrent(id, c, 2200, (i) => observe(i, "arrete", { command: done(i), events: [...i.events, event("commande", "Arrêt constaté")] }));
}

function sellAll(id: string): void {
  assertLive(get(id));
  const c = begin(id, "tout_vendre");
  whenCurrent(id, c, 800, (i) => ({ ...settlePositions(i, "vendre"), command: done(i) }));
}

function setKillSwitch(on: boolean): void {
  set((s) => ({ ...s, killSwitch: on }));
  if (!on) return;
  for (const i of state.instances) {
    const stopping = i.command?.kind === "arreter" && i.command.status === "en_cours";
    if (i.mode !== "backtest" && i.observed !== "arrete" && i.observed !== "achats_en_pause" && !stopping) {
      requestPause(i.id, "Arrêt d'urgence : achats fermés, les ventes continuent");
    }
  }
}

// ---------- paramétrage ----------

function assertEditable(i: Instance, allowReel: boolean): void {
  if (i.mode === "reel" && !allowReel) throw new Error(REEL_MSG);
  if (i.mode === "backtest") {
    const busy = i.backtest?.run.status === "en_cours" || Object.values(i.backtest?.data ?? {}).some((d) => d.status === "import");
    if (busy) throw new Error("Un calcul est en cours : attendre sa fin avant de modifier l'instance.");
    return;
  }
  if (i.observed !== "arrete") throw new Error("Arrêter le bot avant de modifier l'instance.");
  if (selectTrades(state, i.id).some((t) => t.exitTime === undefined)) {
    throw new Error("Des positions sont encore ouvertes : les vendre avant de modifier l'instance.");
  }
}

/** Modifie une instance arrêtée et ajoute une version. `fn` reçoit l'instance et renvoie les champs changés. */
function edit(id: string, summary: string, fn: (i: Instance) => Partial<Instance>, allowReel = false): void {
  const inst = get(id);
  assertEditable(inst, allowReel);
  playStops.get(id)?.();
  patch(id, (i) => ({
    ...i, ...fn(i),
    versions: [...i.versions, { n: i.versions[i.versions.length - 1].n + 1, createdAt: state.cursor, summary }],
  }));
}

/** Un changement de paires ou de réglages rend le résultat du backtest obsolète. */
function resetRun(i: Instance, data?: BacktestConfig["data"], extra: Partial<BacktestConfig> = {}): Pick<Instance, "backtest"> {
  return i.backtest ? { backtest: { ...i.backtest, ...extra, data: data ?? i.backtest.data, run: { status: "jamais", progress: 0 }, playhead: null } } : { backtest: undefined };
}

function strategyOf(strategyId: string): Strategy {
  const s = state.strategies.find((x) => x.id === strategyId);
  if (!s) throw new Error("Stratégie introuvable.");
  return s;
}

function addPair(id: string, pair: string, strategyId: string): void {
  const strategy = strategyOf(strategyId);
  if (!PAIRS.includes(pair)) throw new Error(`Paire inconnue : ${pair}`);
  if (get(id).pairs.some((p) => p.pair === pair)) throw new Error(`${pair} est déjà dans l'instance.`);
  edit(id, `Ajout de ${pair} avec ${strategy.name}`, (i) => ({
    pairs: [...i.pairs, { pair, strategyId }],
    ...(i.backtest && resetRun(i, { ...i.backtest.data, [pair]: { status: "absentes", progress: 0 } })),
  }));
}

function removePair(id: string, pair: string): void {
  if (!get(id).pairs.some((p) => p.pair === pair)) throw new Error(`${pair} n'est pas dans l'instance.`);
  edit(id, `Retrait de ${pair}`, (i) => ({
    pairs: i.pairs.filter((p) => p.pair !== pair),
    ...(i.backtest && resetRun(i, Object.fromEntries(Object.entries(i.backtest.data).filter(([k]) => k !== pair)))),
  }));
}

function setPairStrategy(id: string, pair: string, strategyId: string): void {
  const strategy = strategyOf(strategyId);
  if (!get(id).pairs.some((p) => p.pair === pair)) throw new Error(`${pair} n'est pas dans l'instance.`);
  edit(id, `${pair} : stratégie ${strategy.name}`, (i) => ({
    pairs: i.pairs.map((p) => (p.pair === pair ? { pair, strategyId } : p)), ...resetRun(i),
  }));
}

function setKey(id: string, keyId: string): void {
  const key = state.keys.find((k) => k.id === keyId);
  if (!key) throw new Error("Compte introuvable.");
  const inst = get(id);
  // Seule exception au mode réel : la copie issue de « Passer en réel » n'a pas encore de clé.
  const completesPromotion = inst.mode === "reel" && inst.keyId === null;
  if (completesPromotion && key.env !== "production") throw new Error("Une instance réelle exige un compte de production.");
  if (inst.mode !== "reel" && key.env === "production") throw new Error("Une instance de test exige un compte test.");
  edit(id, `Compte : ${key.name}`, () => ({ keyId, currency: key.currency }), completesPromotion);
}

function toggleAutomation(id: string, automationId: string): void {
  const a = state.automations.find((x) => x.id === automationId);
  if (!a) throw new Error("Automatisation introuvable.");
  const on = get(id).automationIds.includes(automationId);
  edit(id, `${on ? "Automatisation retirée" : "Automatisation ajoutée"} : ${a.name}`, (i) => ({
    automationIds: on ? i.automationIds.filter((x) => x !== automationId) : [...i.automationIds, automationId],
  }));
}

function renameInstance(id: string, name: string): void {
  if (!name.trim()) throw new Error("Le nom ne peut pas être vide.");
  edit(id, `Instance renommée : ${name.trim()}`, () => ({ name: name.trim() }));
}

function setBacktestConfig(id: string, p: Partial<Pick<BacktestConfig, "from" | "to" | "feePct" | "slippagePct">>): void {
  const bt = get(id).backtest;
  if (!bt) throw new Error("Cette instance n'est pas un backtest.");
  const next = { ...bt, ...p };
  if (next.from >= next.to || next.from < EPOCH || next.to > SERIES_END) throw new Error("La période doit tenir dans les 30 jours de données disponibles.");
  if (next.feePct < 0 || next.slippagePct < 0) throw new Error("Les coûts ne peuvent pas être négatifs.");
  edit(id, "Période et coûts du backtest modifiés", (i) => resetRun(i, undefined, p));
}

function createInstance(input: { name: string; mode: Mode; keyId: string | null }): Instance {
  if (input.mode === "reel") throw new Error("Une instance réelle se crée par « Passer en réel » à partir d'une instance de test.");
  if (!input.name.trim()) throw new Error("Le nom ne peut pas être vide.");
  const key = input.keyId ? state.keys.find((k) => k.id === input.keyId) : undefined;
  if (input.keyId && !key) throw new Error("Compte introuvable.");
  if (key?.env === "production") throw new Error("Une instance de test exige un compte test.");
  const inst: Instance = {
    id: uid("inst"), name: input.name.trim(), mode: input.mode, keyId: key?.id ?? null, currency: key?.currency ?? "USDT",
    pairs: [], automationIds: [], startBalance: 2000, wanted: "arrete", observed: "arrete", observedAt: state.cursor, startedAt: null,
    versions: [{ n: 1, createdAt: state.cursor, summary: "Création de l'instance" }], command: null,
    entryPauses: [], manualExits: {}, events: [],
    backtest: input.mode === "backtest" ? newBacktestConfig() : undefined,
  };
  set((s) => ({ ...s, instances: [...s.instances, inst] }));
  return inst;
}

function promote(id: string): Instance {
  const src = get(id);
  if (src.mode !== "test") throw new Error("Seule une instance de test peut passer en réel.");
  const inst: Instance = {
    ...src, id: uid("inst"), name: `${src.name} (réel)`, mode: "reel", promotedFrom: src.id, keyId: null,
    wanted: "arrete", observed: "arrete", observedAt: state.cursor, startedAt: null, command: null,
    entryPauses: [], manualExits: {}, events: [], backtest: undefined,
    versions: [{ n: 1, createdAt: state.cursor, summary: `Copie réelle de ${src.name} (version ${src.versions[src.versions.length - 1].n})` }],
  };
  set((s) => ({ ...s, instances: [...s.instances, inst] }));
  return inst;
}

// ---------- backtest ----------

function backtestOf(id: string): BacktestConfig {
  const i = get(id);
  if (i.mode !== "backtest" || !i.backtest) throw new Error("Cette instance n'est pas un backtest.");
  return i.backtest;
}

function patchBacktest(id: string, fn: (b: BacktestConfig) => BacktestConfig): void {
  patch(id, (i) => (i.backtest ? { ...i, backtest: fn(i.backtest) } : i));
}

function importData(id: string, pair?: string): void {
  const bt = backtestOf(id);
  const names = get(id).pairs.map((p) => p.pair);
  if (pair && !names.includes(pair)) throw new Error(`${pair} n'est pas dans l'instance.`);
  const todo = pair ? [pair] : names.filter((p) => bt.data[p]?.status !== "completes");
  const setData = (p: string, status: "import" | "completes", progress: number) =>
    patchBacktest(id, (b) => ({ ...b, data: { ...b.data, [p]: { status, progress } } }));
  const next = (k: number): void => {
    if (k >= todo.length) return;
    setData(todo[k], "import", 0);
    animate(2500, (p) => setData(todo[k], "import", p), () => { setData(todo[k], "completes", 100); next(k + 1); });
  };
  todo.forEach((p) => setData(p, "import", 0));
  next(0);
}

function runBacktest(id: string): void {
  const bt = backtestOf(id);
  const pairs = get(id).pairs;
  if (!pairs.length) throw new Error("Ajouter au moins une paire avant de lancer le backtest.");
  if (pairs.some((p) => bt.data[p.pair]?.status !== "completes")) throw new Error("Importer les données de toutes les paires avant de lancer le backtest.");
  if (bt.run.status === "en_cours") throw new Error("Le backtest est déjà en cours.");
  playStops.get(id)?.();
  patchBacktest(id, (b) => ({ ...b, run: { status: "en_cours", progress: 0 }, playhead: null }));
  animate(4000, (p) => patchBacktest(id, (b) => ({ ...b, run: { status: "en_cours", progress: p } })),
    () => patchBacktest(id, (b) => ({ ...b, run: { status: "termine", progress: 100 }, playhead: null })));
}

function setPlayhead(id: string, t: number | null): void {
  backtestOf(id);
  patchBacktest(id, (b) => ({ ...b, playhead: t === null ? null : Math.min(Math.max(t, b.from), b.to) }));
}

function pausePlayback(id: string): void {
  playStops.get(id)?.();
  playStops.delete(id);
}

function play(id: string, speed: number): void {
  const bt = backtestOf(id);
  if (bt.run.status !== "termine") throw new Error("Lancer le backtest avant de rejouer la période.");
  pausePlayback(id);
  const stopTimer = every(400, () => {
    const b = backtestOf(id);
    const next = (b.playhead ?? b.from) + speed * BASE_STEP;
    if (next >= b.to) { pausePlayback(id); setPlayhead(id, null); } else setPlayhead(id, next);
  });
  playStops.set(id, () => { stopTimer(); playStops.delete(id); });
}

// ---------- bibliothèque ----------

function addKey(k: { name: string; exchange: string; env: ApiKey["env"]; currency: string; secret: string }): ApiKey {
  if (!k.name.trim()) throw new Error("Le nom ne peut pas être vide.");
  if (k.secret.length < 4) throw new Error("La clé saisie est trop courte.");
  // Le secret n'est jamais gardé : seuls ses 4 derniers caractères servent d'aide-mémoire.
  const key: ApiKey = { id: uid("key"), name: k.name.trim(), exchange: k.exchange, env: k.env, currency: k.currency, createdAt: state.cursor, hint: `…${k.secret.slice(-4)}` };
  set((s) => ({ ...s, keys: [...s.keys, key] }));
  return key;
}

function removeKey(id: string): void {
  const user = state.instances.find((i) => i.keyId === id);
  if (user) throw new Error(`Ce compte est utilisé par « ${user.name} ».`);
  set((s) => ({ ...s, keys: s.keys.filter((k) => k.id !== id) }));
}

function addStrategy(st: Omit<Strategy, "id">): Strategy {
  const strategy = { ...st, id: uid("strat") };
  set((s) => ({ ...s, strategies: [...s.strategies, strategy] }));
  return strategy;
}

function updateStrategy(id: string, p: Partial<Omit<Strategy, "id">>): void {
  const running = state.instances.find((i) => i.observed !== "arrete" && i.pairs.some((x) => x.strategyId === id));
  if (running) throw new Error(`Cette stratégie est utilisée par « ${running.name} », qui tourne : l'arrêter avant de la modifier.`);
  set((s) => ({ ...s, strategies: s.strategies.map((x) => (x.id === id ? { ...x, ...p } : x)) }));
}

function removeStrategy(id: string): void {
  const user = state.instances.find((i) => i.pairs.some((x) => x.strategyId === id));
  if (user) throw new Error(`Cette stratégie est utilisée par « ${user.name} ».`);
  set((s) => ({ ...s, strategies: s.strategies.filter((x) => x.id !== id) }));
}

function addAutomation(a: Omit<Automation, "id">): Automation {
  const automation = { ...a, id: uid("auto") };
  set((s) => ({ ...s, automations: [...s.automations, automation] }));
  return automation;
}

function removeAutomation(id: string): void {
  const user = state.instances.find((i) => i.automationIds.includes(id));
  if (user) throw new Error(`Cette automatisation est utilisée par « ${user.name} ».`);
  set((s) => ({ ...s, automations: s.automations.filter((a) => a.id !== id) }));
}

export const actions = {
  createInstance, addPair, removePair, setPairStrategy, setKey, toggleAutomation, renameInstance, setBacktestConfig,
  start, pauseEntries, resumeEntries, stop, sellAll, promote, setKillSwitch,
  importData, runBacktest, setPlayhead, play, pausePlayback,
  addKey, removeKey, addStrategy, updateStrategy, removeStrategy, addAutomation, removeAutomation,
  setColors: (roles: ColorRoles | null): void => set((s) => ({ ...s, colors: roles })),
  toggleIndicator: (key: string): void =>
    set((s) => ({ ...s, enabledIndicators: s.enabledIndicators.includes(key) ? s.enabledIndicators.filter((k) => k !== key) : [...s.enabledIndicators, key] })),
  setDemo: (p: Partial<State["demo"]>): void => set((s) => ({ ...s, demo: { ...s.demo, ...p } })),
  /** Avance d'une bougie de 5 min (la même chose que l'horloge). */
  tick,
};
