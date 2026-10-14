import { describe, expect, it } from "vitest";

import { fieldsFromSchema, initialValues, validateParams } from "./params-form";

const schema = {
  type: "object",
  required: ["fast"],
  properties: {
    fast: { type: "integer", title: "Fast average", default: 10, minimum: 2, maximum: 50 },
    slow: { type: "integer", default: 30, exclusiveMinimum: 5 },
    ratio: { type: "number", default: 0.5, minimum: 0, maximum: 1, description: "Share of capital" },
    mode: { enum: ["a", "b"], default: "a" },
    note: { type: "string", maxLength: 5 },
    active: { type: "boolean" },
    nested: { type: "object" },
  },
};

describe("form generated from params_schema", () => {
  const { fields, unsupported } = fieldsFromSchema(schema);

  it("one field per supported property, with type, label, bounds and default", () => {
    expect(fields.map((f) => [f.key, f.kind])).toEqual([["fast", "integer"], ["slow", "integer"], ["ratio", "number"], ["mode", "enum"], ["note", "string"], ["active", "boolean"]]);
    const fast = fields[0]!;
    expect(fast).toMatchObject({ label: "Fast average", min: 2, max: 50, required: true, initial: "10" });
    expect(fields[1]).toMatchObject({ min: 5, minExclusive: true });
    expect(fields[2]!.description).toBe("Share of capital");
  });

  it("does not hide what it cannot render", () => {
    expect(unsupported).toEqual(["nested"]);
  });

  it("initial values: schema defaults, boolean unchecked", () => {
    expect(initialValues(fields)).toEqual({ fast: "10", slow: "30", ratio: "0.5", mode: "a", note: "", active: "false" });
  });

  it("accepts the defaults and does not send an empty optional field", () => {
    const { values, errors } = validateParams(fields, initialValues(fields));
    expect(errors).toEqual({});
    expect(values).toEqual({ fast: 10, slow: 30, ratio: 0.5, mode: "a", active: false });
  });

  it("refuses type, bounds, enum, length and an empty required field", () => {
    const { errors } = validateParams(fields, { fast: "1.5", slow: "5", ratio: "1,2", mode: "z", note: "too long!", active: "true" });
    expect(errors.fast).toEqual({ code: "integer" });
    expect(errors.slow).toEqual({ code: "min", bound: 5, exclusive: true });
    expect(errors.ratio).toEqual({ code: "max", bound: 1, exclusive: false });
    expect(errors.mode).toEqual({ code: "enum" });
    expect(errors.note).toEqual({ code: "maxLength", bound: 5 });
    expect(validateParams(fields, { ...initialValues(fields), fast: "" }).errors.fast).toEqual({ code: "required" });
    expect(validateParams(fields, { ...initialValues(fields), fast: "51" }).errors.fast).toMatchObject({ code: "max" });
    expect(validateParams(fields, { ...initialValues(fields), fast: "abc" }).errors.fast).toEqual({ code: "integer" });
  });

  it("accepts the decimal comma and refuses an exponent", () => {
    expect(validateParams(fields, { ...initialValues(fields), ratio: "0,25" }).values.ratio).toBe(0.25);
    expect(validateParams(fields, { ...initialValues(fields), ratio: "1e-1" }).errors.ratio).toEqual({ code: "number" });
  });

  it("empty or unreadable schema: no field", () => {
    expect(fieldsFromSchema({})).toEqual({ fields: [], unsupported: [] });
    expect(fieldsFromSchema(null)).toEqual({ fields: [], unsupported: [] });
  });
});
