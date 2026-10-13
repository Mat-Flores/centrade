import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  INITIAL_CURSOR, actions, getState, resetStore, selectCandles, selectLog, selectStats, selectTrades, startClock, stopClock, subscribe,
} from "./store";
import { EPOCH } from "./sim";
import { ftTemplate } from "./providers";

const inst = (id: string) => getState().instances.find((i) => i.id === id)!;
const wait = (ms: number) => vi.advanceTimersByTime(ms);

beforeEach(() => { vi.useFakeTimers(); resetStore(); });
afterEach(() => { resetStore(); vi.useRealTimers(); });

describe("graines", () => {
  it("curseur initial et instances", () => {
    expect(getState().cursor).toBe(EPOCH + 24 * 86400);
    expect(getState().cursor).toBe(INITIAL_CURSOR);
    expect(getState().instances.map((i) => i.name)).toEqual(["Swing majors", "Prod prudente", "Essai tendance", "Brouillon altcoins"]);
    expect(inst("inst-swing").versions).toHaveLength(4);
  });
  it("l'instance en cours a des trades, des stats et un journal chronologique", () => {
    const s = getState();
    expect(selectTrades(s, "inst-swing").length).toBeGreaterThan(5);
    expect(selectStats(s, "inst-swing").balance).toBeCloseTo(2000 + selectStats(s, "inst-swing").realized + selectStats(s, "inst-swing").unrealized);
    const log = selectLog(s, "inst-swing");
    expect(log.some((e) => e.kind === "achat_refuse")).toBe(true);
    expect(log.some((e) => /^Vente [A-Z]+\/USDT, /.test(e.text))).toBe(true);
    expect(log.map((e) => e.time)).toEqual([...log.map((e) => e.time)].sort((a, b) => a - b));
    expect(selectStats(s, "inst-swing", "BTC/USDT").trades).toBeLessThanOrEqual(selectStats(s, "inst-swing").trades);
  });
  it("rien à montrer pour une instance jamais démarrée ou un backtest non lancé", () => {
    expect(selectTrades(getState(), "inst-brouillon")).toEqual([]);
    expect(selectTrades(getState(), "inst-essai")).toEqual([]);
  });
  it("les sélecteurs sont stables quand rien ne change", () => {
    const s = getState();
    expect(selectTrades(s, "inst-swing")).toBe(selectTrades(s, "inst-swing"));
    expect(selectStats(s, "inst-swing")).toBe(selectStats(s, "inst-swing"));
    expect(selectCandles(s, "inst-swing", "BTC/USDT", "1h")).toBe(selectCandles(s, "inst-swing", "BTC/USDT", "1h"));
  });
  it("les bougies s'arrêtent au curseur", () => {
    const c = selectCandles(getState(), "inst-swing", "BTC/USDT", "5m");
    expect(c[c.length - 1].time).toBe(INITIAL_CURSOR);
  });
});

describe("horloge", () => {
  it("avance d'une bougie par tick et met à jour observedAt", () => {
    startClock();
    wait(1500);
    expect(getState().cursor).toBe(INITIAL_CURSOR + 300);
    expect(inst("inst-swing").observedAt).toBe(INITIAL_CURSOR + 300);
    expect(inst("inst-brouillon").observedAt).toBe(INITIAL_CURSOR);
    stopClock();
  });
  it("données figées : le curseur avance, observedAt reste", () => {
    actions.setDemo({ frozen: true });
    startClock();
    wait(3000);
    expect(getState().cursor).toBe(INITIAL_CURSOR + 600);
    expect(inst("inst-swing").observedAt).toBe(INITIAL_CURSOR);
    stopClock();
  });
  it("resetStore arrête l'horloge", () => {
    startClock();
    resetStore();
    wait(5000);
    expect(getState().cursor).toBe(INITIAL_CURSOR);
  });
});

describe("démarrage", () => {
  const ready = () => {
    actions.setKey("inst-brouillon", "key-binance-test");
    return "inst-brouillon";
  };
  it("refuse sans paire, sans compte, sous arrêt d'urgence", () => {
    const n = actions.createInstance({ name: "Vide", mode: "test", keyId: "key-binance-test" });
    expect(() => actions.start(n.id)).toThrow(/paire/);
    expect(() => actions.start("inst-brouillon")).toThrow(/compte/);
    ready();
    actions.setKillSwitch(true);
    expect(() => actions.start("inst-brouillon")).toThrow(/arrêt d'urgence/);
  });
  it("refuse un backtest", () => expect(() => actions.start("inst-essai")).toThrow());
  it("l'état constaté suit la commande, jamais avant", () => {
    const id = ready();
    actions.start(id);
    expect(inst(id).wanted).toBe("actif");
    expect(inst(id).observed).toBe("arrete");
    expect(inst(id).command?.status).toBe("en_cours");
    wait(300);
    expect(inst(id).observed).toBe("lancement");
    wait(1000);
    expect(inst(id).observed).toBe("verification");
    expect(inst(id).command?.steps?.map((s) => s.status)).toEqual(["ok", "en_cours", "attente"]);
    wait(2000);
    expect(inst(id).command?.steps?.[1].detail).toContain("Version 2 chargée");
    wait(800);
    expect(inst(id).observed).toBe("actif");
    expect(inst(id).command?.status).toBe("constatee");
    expect(inst(id).startedAt).toBe(getState().cursor);
  });
  it("échec de vérification : bot en pause d'achats, drapeau remis à zéro", () => {
    const id = ready();
    actions.setDemo({ failNextStart: true });
    actions.start(id);
    wait(5000);
    expect(inst(id).observed).toBe("achats_en_pause");
    expect(inst(id).command?.status).toBe("echouee");
    expect(inst(id).command?.steps?.[1]).toMatchObject({ status: "echec", detail: "Configuration relue : 1 écart (taille des positions)" });
    expect(getState().demo.failNextStart).toBe(false);
    expect(inst(id).entryPauses).toHaveLength(1);
  });
});

describe("paramétrage", () => {
  it("modifie une instance arrêtée et crée une version", () => {
    actions.addPair("inst-brouillon", "SOL/USDT", "strat-croisement");
    expect(inst("inst-brouillon").pairs).toHaveLength(2);
    expect(inst("inst-brouillon").versions.at(-1)).toMatchObject({ n: 2, summary: "Ajout de SOL/USDT avec Croisement de moyennes" });
    actions.removePair("inst-brouillon", "SOL/USDT");
    expect(inst("inst-brouillon").versions).toHaveLength(3);
  });
  it("refuse tant que le bot tourne", () => {
    expect(() => actions.renameInstance("inst-swing", "X")).toThrow(/Arrêter/);
  });
  it("refuse une instance réelle avec le message prévu", () => {
    expect(() => actions.addPair("inst-prod", "SOL/USDT", "strat-tendance")).toThrow(
      "Une instance en mode réel ne se modifie pas : modifier l'instance de test, puis repasser en réel.",
    );
  });
  it("refuse tant qu'une position est ouverte", () => {
    actions.stop("inst-swing", { sellAll: false });
    wait(3000);
    expect(inst("inst-swing").observed).toBe("arrete");
    const open = selectTrades(getState(), "inst-swing").filter((t) => t.exitTime === undefined);
    if (open.length) expect(() => actions.renameInstance("inst-swing", "X")).toThrow(/positions/);
    expect(inst("inst-swing").events.some((e) => e.kind === "alerte" && /sans bot/.test(e.text)) ).toBe(open.length > 0);
  });
});

describe("pause, reprise, arrêt", () => {
  it("pause puis reprise", () => {
    actions.pauseEntries("inst-swing");
    expect(inst("inst-swing").observed).toBe("actif");
    wait(600);
    expect(inst("inst-swing").observed).toBe("achats_en_pause");
    actions.resumeEntries("inst-swing");
    wait(1500);
    expect(inst("inst-swing").observed).toBe("actif");
    expect(inst("inst-swing").entryPauses.every((p) => p.to !== null)).toBe(true);
  });
  it("reprise refusée sous arrêt d'urgence ou si l'observation est périmée", () => {
    actions.pauseEntries("inst-swing");
    wait(600);
    actions.setDemo({ frozen: true });
    startClock();
    wait(1500 * 13);
    stopClock();
    expect(() => actions.resumeEntries("inst-swing")).toThrow(/périmé/);
    actions.setDemo({ frozen: false });
    actions.setKillSwitch(true);
    expect(() => actions.resumeEntries("inst-swing")).toThrow(/arrêt d'urgence/);
  });
  it("tout vendre ferme les positions ouvertes, cause manuelle", () => {
    const before = selectTrades(getState(), "inst-swing").filter((t) => t.exitTime === undefined).length;
    expect(before).toBeGreaterThan(0);
    actions.sellAll("inst-swing");
    wait(800);
    const after = selectTrades(getState(), "inst-swing");
    expect(after.filter((t) => t.exitTime === undefined)).toHaveLength(0);
    expect(after.filter((t) => t.exitCause === "manual")).toHaveLength(before);
    expect(inst("inst-swing").command?.status).toBe("constatee");
  });
  it("arrêt avec vente : pause des achats, vente, puis arrêté", () => {
    actions.stop("inst-swing", { sellAll: true });
    wait(700);
    expect(inst("inst-swing").observed).toBe("achats_en_pause");
    wait(1600);
    expect(inst("inst-swing").observed).toBe("arrete");
    expect(selectTrades(getState(), "inst-swing").some((t) => t.exitTime === undefined)).toBe(false);
    expect(() => actions.stop("inst-swing", { sellAll: true })).toThrow();
  });
  it("arrêt d'urgence : met en pause les bots qui tournent, ne reprend rien en se désactivant", () => {
    actions.setKillSwitch(true);
    wait(700);
    expect(inst("inst-swing").observed).toBe("achats_en_pause");
    expect(inst("inst-prod").observed).toBe("achats_en_pause");
    actions.setKillSwitch(false);
    wait(5000);
    expect(inst("inst-swing").observed).toBe("achats_en_pause");
  });
});

describe("promotion et bibliothèque", () => {
  it("promote copie une instance de test en réel arrêté sans clé", () => {
    const r = actions.promote("inst-swing");
    expect(r).toMatchObject({ mode: "reel", name: "Swing majors (réel)", promotedFrom: "inst-swing", keyId: null, observed: "arrete" });
    expect(r.pairs).toEqual(inst("inst-swing").pairs);
    expect(() => actions.promote("inst-prod")).toThrow();
    expect(() => actions.setKey(r.id, "key-binance-test")).toThrow();
    actions.setKey(r.id, "key-binance-prod");
    expect(inst(r.id).keyId).toBe("key-binance-prod");
    expect(() => actions.setKey(r.id, "key-binance-prod")).toThrow(/réel/);
  });
  it("une instance réelle ne se crée pas directement", () => {
    expect(() => actions.createInstance({ name: "X", mode: "reel", keyId: null })).toThrow();
  });
  it("addKey ne garde que 4 caractères du secret", () => {
    const k = actions.addKey({ name: "Test", exchange: "Binance", env: "test", currency: "USDT", secret: "aaaaaaaaaaaa7890" });
    expect(k.hint).toBe("…7890");
    expect(JSON.stringify(getState())).not.toContain("aaaaaaaaaaaa7890");
  });
  it("suppressions refusées si utilisé", () => {
    expect(() => actions.removeKey("key-binance-test")).toThrow(/utilisé/);
    expect(() => actions.removeStrategy("strat-retour")).toThrow(/utilisée/);
    expect(() => actions.updateStrategy("strat-croisement", { stopLossPct: 4 })).toThrow(/tourne/);
    expect(() => actions.removeAutomation("auto-pause-perte")).toThrow(/utilisée/);
    actions.removeKey("key-kraken-test");
    expect(getState().keys).toHaveLength(2);
    const a = actions.addAutomation({ kind: "alerte", name: "Test", description: "d" });
    actions.removeAutomation(a.id);
    const st = actions.addStrategy({ name: "N", description: "", provider: "freqtrade", className: "N", code: ftTemplate("N"), trailing: false, timeframe: "1h", extraTimeframes: [], stopLossPct: 1, takeProfitPct: 2, params: {} });
    actions.updateStrategy(st.id, { stopLossPct: 2 });
    actions.removeStrategy(st.id);
  });
  it("une stratégie ne sert que dans une instance de son provider", () => {
    expect(() => actions.createInstance({ name: "N", mode: "test", keyId: null, provider: "nautilus" })).toThrow(/pas encore pris en charge/);
    expect(() => actions.addStrategy({ name: "N", description: "", provider: "freqtrade", className: "N", code: "class N: pass", trailing: false, timeframe: "1h", extraTimeframes: [], stopLossPct: 1, takeProfitPct: 2, params: {} })).toThrow(/Contrôle du code/);
    // une stratégie d'un autre provider, posée telle quelle dans l'état : l'affectation est refusée
    const foreign = { ...getState().strategies[0], id: "strat-x", provider: "nautilus" as const };
    getState().strategies.push(foreign);
    expect(() => actions.addPair("inst-brouillon", "SOL/USDT", "strat-x")).toThrow(/NautilusTrader/);
    expect(() => actions.setPairStrategy("inst-brouillon", "DOGE/USDT", "strat-x")).toThrow(/NautilusTrader/);
    expect(() => actions.setProvider("inst-brouillon", "freqtrade")).not.toThrow();
    expect(() => actions.setProvider("inst-swing", "nautilus")).toThrow();
  });
  it("indicateurs, couleurs", () => {
    expect(getState().enabledIndicators).toEqual(["winRate", "profitFactor", "maxDrawdownPct", "openPositions", "fees", "avgDurationSec"]);
    actions.toggleIndicator("sharpe");
    actions.toggleIndicator("winRate");
    expect(getState().enabledIndicators).toContain("sharpe");
    expect(getState().enabledIndicators).not.toContain("winRate");
  });
  it("les abonnés sont notifiés", () => {
    const l = vi.fn();
    const off = subscribe(l);
    actions.setDemo({ frozen: true });
    off();
    actions.setDemo({ frozen: false });
    expect(l).toHaveBeenCalledTimes(1);
  });
});

describe("backtest", () => {
  it("import, lancement, lecture", () => {
    expect(() => actions.runBacktest("inst-essai")).toThrow(/Importer/);
    actions.importData("inst-essai");
    expect(inst("inst-essai").backtest?.data["ETH/USDT"].status).toBe("import");
    wait(2500 + 100);
    expect(inst("inst-essai").backtest?.data["ETH/USDT"].status).toBe("completes");
    expect(inst("inst-essai").backtest?.data["LINK/USDT"].status).toBe("import");
    wait(2500 + 100);
    expect(Object.values(inst("inst-essai").backtest!.data).every((d) => d.status === "completes")).toBe(true);
    actions.runBacktest("inst-essai");
    wait(1000);
    expect(inst("inst-essai").backtest?.run.status).toBe("en_cours");
    expect(() => actions.renameInstance("inst-essai", "X")).toThrow(/calcul/);
    wait(3100);
    expect(inst("inst-essai").backtest?.run).toEqual({ status: "termine", progress: 100 });
    const all = selectTrades(getState(), "inst-essai");
    expect(all.length).toBeGreaterThan(0);
    expect(all.every((t) => t.exitTime !== undefined || t.entryTime <= EPOCH + 21 * 86400)).toBe(true);

    actions.setPlayhead("inst-essai", EPOCH + 5 * 86400);
    const early = selectTrades(getState(), "inst-essai");
    expect(early.every((t) => t.entryTime <= EPOCH + 5 * 86400)).toBe(true);
    const c = selectCandles(getState(), "inst-essai", "BTC/USDT", "4h");
    expect(c.at(-1)!.time).toBeLessThanOrEqual(EPOCH + 5 * 86400);

    actions.play("inst-essai", 12);
    wait(400);
    expect(inst("inst-essai").backtest?.playhead).toBe(EPOCH + 5 * 86400 + 12 * 300);
    actions.pausePlayback("inst-essai");
    wait(2000);
    expect(inst("inst-essai").backtest?.playhead).toBe(EPOCH + 5 * 86400 + 12 * 300);
  });
  it("modifier la configuration invalide le résultat", () => {
    actions.importData("inst-essai");
    wait(10000);
    actions.runBacktest("inst-essai");
    wait(4100);
    actions.setBacktestConfig("inst-essai", { feePct: 0.2 });
    expect(inst("inst-essai").backtest?.run.status).toBe("jamais");
    expect(() => actions.setBacktestConfig("inst-essai", { from: EPOCH + 100 * 86400 })).toThrow(/période/);
  });
});
