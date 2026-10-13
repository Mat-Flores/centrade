import { beforeEach, describe, expect, it } from "vitest";
import { canSwap, layout, slotOf } from "./layout";

const snapshot = () => layout.get();

describe("disposition", () => {
  beforeEach(() => layout.reset());
  it("deux zones de la grille s'échangent, pas une zone du haut avec la grille", () => {
    const before = snapshot();
    expect(canSwap(before, "comp", "journal")).toBe(true);
    expect(canSwap(before, "balance", "chart")).toBe(false);
    layout.swap("comp", "journal");
    expect(slotOf(snapshot(), "journal")).toBe(2);
    expect(slotOf(snapshot(), "comp")).toBe(5);
    layout.swap("balance", "chart");
    expect(slotOf(snapshot(), "balance")).toBe(0);
  });
  it("reset revient au défaut", () => {
    layout.swap("balance", "ind"); layout.toggle("chart"); layout.setCenterH(0, 300);
    layout.reset();
    const l = snapshot();
    expect(l.slots).toEqual(["balance", "ind", "comp", "chart", "pairs", "journal"]);
    expect(l.closed.chart).toBe(false);
    expect(l.centerH).toEqual([520, 240]);
  });
});
