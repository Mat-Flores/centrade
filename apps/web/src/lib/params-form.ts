/**
 * Formulaire de déploiement généré depuis `params_schema` du manifest (SPEC §9, écran 2).
 * Sous-ensemble du JSON Schema pris en charge : propriétés scalaires (integer, number, string, boolean, enum)
 * avec `default`, `minimum`/`maximum`, `exclusiveMinimum`/`exclusiveMaximum`, `minLength`/`maxLength`, `required`.
 * Une propriété d'un autre genre (objet, tableau…) n'est jamais ignorée en silence : elle est rendue dans
 * `unsupported`, et l'écran le dit. La validation d'ici évite un aller-retour inutile ; l'API valide à son tour.
 * shortcut: les paramètres numériques partent en nombres JSON (ce sont des réglages, pas de l'argent) ;
 * un paramètre monétaire passerait par une chaîne décimale.
 */

export type FieldKind = "integer" | "number" | "string" | "boolean" | "enum";

export interface Field {
  key: string;
  kind: FieldKind;
  label: string;
  description: string | null;
  required: boolean;
  /** Valeur par défaut du schéma, déjà en texte de saisie ; `null` : aucune. */
  initial: string | null;
  options: string[];
  min: number | null;
  max: number | null;
  minExclusive: boolean;
  maxExclusive: boolean;
  minLength: number | null;
  maxLength: number | null;
}

export type FieldError =
  | { code: "required" }
  | { code: "integer" }
  | { code: "number" }
  | { code: "min"; bound: number; exclusive: boolean }
  | { code: "max"; bound: number; exclusive: boolean }
  | { code: "minLength"; bound: number }
  | { code: "maxLength"; bound: number }
  | { code: "enum" };

type Raw = Record<string, unknown>;
const isRecord = (v: unknown): v is Raw => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Bornes d'un schéma : `exclusiveMinimum` numérique (draft 6+) l'emporte sur `minimum`. */
function bound(p: Raw, low: boolean): { value: number | null; exclusive: boolean } {
  const exclusive = num(p[low ? "exclusiveMinimum" : "exclusiveMaximum"]);
  if (exclusive !== null) return { value: exclusive, exclusive: true };
  return { value: num(p[low ? "minimum" : "maximum"]), exclusive: false };
}

export function fieldsFromSchema(schema: unknown): { fields: Field[]; unsupported: string[] } {
  const props = isRecord(schema) && isRecord(schema.properties) ? schema.properties : {};
  const required = new Set(isRecord(schema) && Array.isArray(schema.required) ? schema.required.filter((x): x is string => typeof x === "string") : []);
  const fields: Field[] = [];
  const unsupported: string[] = [];
  for (const [key, raw] of Object.entries(props)) {
    if (!isRecord(raw)) {
      unsupported.push(key);
      continue;
    }
    const options = Array.isArray(raw.enum) ? raw.enum.filter((x): x is string | number => typeof x === "string" || typeof x === "number").map(String) : [];
    const kind: FieldKind | null =
      options.length > 0 && Array.isArray(raw.enum) && options.length === raw.enum.length
        ? "enum"
        : raw.type === "integer" || raw.type === "number" || raw.type === "string" || raw.type === "boolean"
          ? raw.type
          : null;
    if (kind === null) {
      unsupported.push(key);
      continue;
    }
    const lo = bound(raw, true);
    const hi = bound(raw, false);
    const def = raw.default;
    fields.push({
      key,
      kind,
      label: typeof raw.title === "string" && raw.title ? raw.title : key,
      description: typeof raw.description === "string" && raw.description ? raw.description : null,
      required: required.has(key),
      initial: typeof def === "string" || typeof def === "number" || typeof def === "boolean" ? String(def) : kind === "boolean" ? "false" : null,
      options,
      min: lo.value,
      max: hi.value,
      minExclusive: lo.exclusive,
      maxExclusive: hi.exclusive,
      minLength: num(raw.minLength),
      maxLength: num(raw.maxLength),
    });
  }
  return { fields, unsupported };
}

export function initialValues(fields: readonly Field[]): Record<string, string> {
  return Object.fromEntries(fields.map((f) => [f.key, f.initial ?? ""]));
}

const INTEGER = /^[+-]?\d+$/;
const NUMBER = /^[+-]?(\d+([.,]\d+)?|[.,]\d+)$/;

/** Valide la saisie champ par champ ; `values` ne contient que ce qui sera envoyé (un champ facultatif vide est omis). */
export function validateParams(fields: readonly Field[], raw: Readonly<Record<string, string>>): { values: Record<string, string | number | boolean>; errors: Record<string, FieldError> } {
  const values: Record<string, string | number | boolean> = {};
  const errors: Record<string, FieldError> = {};
  for (const f of fields) {
    const text = (raw[f.key] ?? "").trim();
    if (f.kind === "boolean") {
      values[f.key] = text === "true";
      continue;
    }
    if (text === "") {
      if (f.required) errors[f.key] = { code: "required" };
      continue;
    }
    if (f.kind === "enum") {
      if (f.options.includes(text)) values[f.key] = text;
      else errors[f.key] = { code: "enum" };
      continue;
    }
    if (f.kind === "string") {
      if (f.minLength !== null && text.length < f.minLength) errors[f.key] = { code: "minLength", bound: f.minLength };
      else if (f.maxLength !== null && text.length > f.maxLength) errors[f.key] = { code: "maxLength", bound: f.maxLength };
      else values[f.key] = text;
      continue;
    }
    if (!(f.kind === "integer" ? INTEGER : NUMBER).test(text)) {
      errors[f.key] = { code: f.kind === "integer" ? "integer" : "number" };
      continue;
    }
    const n = Number(text.replace(",", "."));
    if (f.min !== null && (f.minExclusive ? n <= f.min : n < f.min)) errors[f.key] = { code: "min", bound: f.min, exclusive: f.minExclusive };
    else if (f.max !== null && (f.maxExclusive ? n >= f.max : n > f.max)) errors[f.key] = { code: "max", bound: f.max, exclusive: f.maxExclusive };
    else values[f.key] = n;
  }
  return { values, errors };
}
