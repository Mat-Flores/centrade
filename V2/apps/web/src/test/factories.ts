// Test-only factories: never imported by app code, so never part of the bundle.
import type { Account } from "@/lib/accounts";
import type { Alert, Command, Instance } from "@/lib/instances";

export const NOW = Date.parse("2026-10-11T15:00:00Z");
export const iso = (secondsAgo: number) => new Date(NOW - secondsAgo * 1000).toISOString();

/** `age`: seconds since the engine was last observed; `null`: never observed. */
export function makeInstance(over: Partial<Instance> & { stateValue?: Instance["state"]["value"]; age?: number | null } = {}): Instance {
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
    strategy: null,
    account: null,
    started_at: null,
    realized_pnl: { value: age === null ? null : [], observed_at: observedAt, stale: false },
    closed_trades: { value: age === null ? null : 0, observed_at: observedAt, stale: false },
    open_positions: { value: age === null ? null : 0, observed_at: observedAt, stale: false },
    created_at: iso(3600),
    server_time: iso(0),
    ...rest,
  };
}

export function makeCommand(over: Partial<Command> = {}): Command {
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

export const makeAlert = (id: string, over: Partial<Alert> = {}): Alert => ({
  id,
  rule: "r",
  severity: "critical",
  target_kind: "instance",
  status: "open",
  message: "The observed mode differs from the wanted mode.",
  created_at: iso(5),
  ...over,
});

export const makeAccount = (over: Partial<Account> = {}): Account => ({
  id: "a-1",
  venue: "binance",
  type: "paper",
  environment: "sandbox",
  label: "Paper account",
  currency: "USDT",
  capital_cap: null,
  trade_key: null,
  read_key: null,
  permissions_verified_at: null,
  ip_restricted: null,
  created_at: iso(7200),
  updated_at: iso(7200),
  ...over,
});

/** Copy of a wire object without one key: builds out-of-contract responses. */
export const without = (value: object, key: string): Record<string, unknown> =>
  Object.fromEntries(Object.entries(value).filter(([k]) => k !== key));
