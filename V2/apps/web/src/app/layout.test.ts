import { beforeEach, describe, expect, it } from "vitest";
import { canSwap, layout, slotOf } from "./layout";

const snapshot = () => layout.get();

describe("dashboard layout", () => {
  beforeEach(() => layout.reset());
  it("swaps two grid zones but not a top zone with a grid zone", () => {
    const before = snapshot();
    expect(canSwap(before, "composition", "journal")).toBe(true);
    expect(canSwap(before, "balance", "chart")).toBe(false);
    layout.swap("composition", "journal");
    expect(slotOf(snapshot(), "journal")).toBe(2);
    expect(slotOf(snapshot(), "composition")).toBe(5);
    layout.swap("balance", "chart");
    expect(slotOf(snapshot(), "balance")).toBe(0);
  });
  it("goes back to the default layout on reset", () => {
    layout.swap("balance", "indicators"); layout.toggle("chart"); layout.setCenterH(0, 300);
    layout.reset();
    const l = snapshot();
    expect(l.slots).toEqual(["balance", "indicators", "composition", "chart", "pairs", "journal"]);
    expect(l.closed.chart).toBe(false);
    expect(l.centerH).toEqual([520, 240]);
  });
});
