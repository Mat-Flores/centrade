import { describe, expect, it } from "vitest";

import { fieldsFromSchema, initialValues, validateParams } from "./params-form";

const schema = {
  type: "object",
  required: ["fast"],
  properties: {
    fast: { type: "integer", title: "Moyenne rapide", default: 10, minimum: 2, maximum: 50 },
    slow: { type: "integer", default: 30, exclusiveMinimum: 5 },
    ratio: { type: "number", default: 0.5, minimum: 0, maximum: 1, description: "Part du capital" },
    mode: { enum: ["a", "b"], default: "a" },
    note: { type: "string", maxLength: 5 },
    active: { type: "boolean" },
    nested: { type: "object" },
  },
};

describe("formulaire généré depuis params_schema", () => {
  const { fields, unsupported } = fieldsFromSchema(schema);

  it("un champ par propriété prise en charge, avec type, libellé, bornes et défaut", () => {
    expect(fields.map((f) => [f.key, f.kind])).toEqual([["fast", "integer"], ["slow", "integer"], ["ratio", "number"], ["mode", "enum"], ["note", "string"], ["active", "boolean"]]);
    const fast = fields[0]!;
    expect(fast).toMatchObject({ label: "Moyenne rapide", min: 2, max: 50, required: true, initial: "10" });
    expect(fields[1]).toMatchObject({ min: 5, minExclusive: true });
    expect(fields[2]!.description).toBe("Part du capital");
  });

  it("ne cache pas ce qu'il ne sait pas rendre", () => {
    expect(unsupported).toEqual(["nested"]);
  });

  it("valeurs initiales : défauts du schéma, booléen décoché", () => {
    expect(initialValues(fields)).toEqual({ fast: "10", slow: "30", ratio: "0.5", mode: "a", note: "", active: "false" });
  });

  it("accepte les défauts et n'envoie pas un champ facultatif vide", () => {
    const { values, errors } = validateParams(fields, initialValues(fields));
    expect(errors).toEqual({});
    expect(values).toEqual({ fast: 10, slow: 30, ratio: 0.5, mode: "a", active: false });
  });

  it("refuse type, bornes, énumération, longueur et champ obligatoire vide", () => {
    const { errors } = validateParams(fields, { fast: "1.5", slow: "5", ratio: "1,2", mode: "z", note: "trop long", active: "true" });
    expect(errors.fast).toEqual({ code: "integer" });
    expect(errors.slow).toEqual({ code: "min", bound: 5, exclusive: true });
    expect(errors.ratio).toEqual({ code: "max", bound: 1, exclusive: false });
    expect(errors.mode).toEqual({ code: "enum" });
    expect(errors.note).toEqual({ code: "maxLength", bound: 5 });
    expect(validateParams(fields, { ...initialValues(fields), fast: "" }).errors.fast).toEqual({ code: "required" });
    expect(validateParams(fields, { ...initialValues(fields), fast: "51" }).errors.fast).toMatchObject({ code: "max" });
    expect(validateParams(fields, { ...initialValues(fields), fast: "abc" }).errors.fast).toEqual({ code: "integer" });
  });

  it("accepte la virgule décimale de saisie et refuse un exposant", () => {
    expect(validateParams(fields, { ...initialValues(fields), ratio: "0,25" }).values.ratio).toBe(0.25);
    expect(validateParams(fields, { ...initialValues(fields), ratio: "1e-1" }).errors.ratio).toEqual({ code: "number" });
  });

  it("schéma vide ou illisible : aucun champ", () => {
    expect(fieldsFromSchema({})).toEqual({ fields: [], unsupported: [] });
    expect(fieldsFromSchema(null)).toEqual({ fields: [], unsupported: [] });
  });
});
