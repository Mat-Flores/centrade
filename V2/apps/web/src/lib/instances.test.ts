import { describe, expect, it } from "vitest";

import { makeInstance, without } from "@/test/factories";

import { INSTANCE_NAME_MAX_LENGTH, InstanceDetailSchema, InstanceSchema, isValidInstanceName } from "./instances";

const wire = () => JSON.parse(JSON.stringify(makeInstance())) as Record<string, unknown>;

describe("InstanceSchema", () => {
  it("accepts an instance with its strategy, account, start time and aggregates", () => {
    const full = makeInstance({
      strategy: { version_id: "v-1", strategy_id: "s-1", name: "sma", version: 3, status: "approved", code_hash: "abc", exits: { stoploss: "-0.05" } },
      account: { id: "a-1", venue: "binance", type: "paper", environment: "sandbox", label: "Paper", currency: "USDT" },
      started_at: "2026-10-11T14:00:00Z",
      realized_pnl: { value: [{ currency: "USDT", amount: "12.5", fees: "0.3" }], observed_at: "2026-10-11T14:59:58Z", stale: false },
      closed_trades: { value: 4, observed_at: "2026-10-11T14:59:58Z", stale: false },
      open_positions: { value: 1, observed_at: "2026-10-11T14:59:58Z", stale: false },
    });
    expect(InstanceSchema.safeParse(full).success).toBe(true);
  });

  it("accepts a never-observed aggregate as null, which stays unknown", () => {
    const parsed = InstanceSchema.parse({ ...wire(), open_positions: { value: null, observed_at: null, stale: false } });
    expect(parsed.open_positions.value).toBeNull();
  });

  it.each(["strategy", "account", "started_at", "realized_pnl", "closed_trades", "open_positions"])("refuses a response without %s", (field) => {
    expect(InstanceSchema.safeParse(without(wire(), field)).success).toBe(false);
  });

  it("refuses a monetary amount that is a number instead of a decimal string", () => {
    const body = { ...wire(), realized_pnl: { value: [{ currency: "USDT", amount: 12.5, fees: "0" }], observed_at: null, stale: false } };
    expect(InstanceSchema.safeParse(body).success).toBe(false);
  });

  it("accepts balances while absent from the server contract, and reads them when present", () => {
    expect(InstanceSchema.safeParse(wire()).success).toBe(true);
    const withBalances = { ...wire(), balances: { value: [{ currency: "USDT", free: "10", total: "12" }], observed_at: null, stale: false } };
    expect(InstanceSchema.parse(withBalances).balances?.value?.[0]?.total).toBe("12");
    expect(InstanceSchema.safeParse({ ...wire(), balances: { value: [{ currency: "USDT", free: 10, total: "12" }], observed_at: null, stale: false } }).success).toBe(false);
  });

  it("makes the detail inherit the list contract", () => {
    const detail = {
      ...wire(),
      deployment_fingerprint: null,
      config_hash: null,
      engine_version: { value: null, observed_at: null, stale: false },
      effective_config: { value: null, observed_at: null, stale: false },
      drift: { value: null, observed_at: null, stale: false },
    };
    expect(InstanceDetailSchema.safeParse(detail).success).toBe(true);
    expect(InstanceDetailSchema.safeParse(without(detail, "strategy")).success).toBe(false);
  });
});

describe("isValidInstanceName", () => {
  it("accepts letters, digits, dot, dash and underscore after a letter or digit", () => {
    expect(isValidInstanceName("alpha-1.test_2")).toBe(true);
  });
  it("refuses a leading symbol, spaces, an empty name and a name over the maximum length", () => {
    expect(isValidInstanceName("-alpha")).toBe(false);
    expect(isValidInstanceName("al pha")).toBe(false);
    expect(isValidInstanceName("")).toBe(false);
    expect(isValidInstanceName("a".repeat(INSTANCE_NAME_MAX_LENGTH))).toBe(true);
    expect(isValidInstanceName("a".repeat(INSTANCE_NAME_MAX_LENGTH + 1))).toBe(false);
  });
});
