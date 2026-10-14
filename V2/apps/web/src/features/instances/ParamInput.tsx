import { fr } from "@/i18n/fr";
import type { Field as ParamField, FieldError } from "@/lib/params-form";
import { Field } from "@/ui/ui";

const t = fr.instances.deploy;

function errorText(e: FieldError): string {
  switch (e.code) {
    case "min": return t.params.min(e.bound, e.exclusive);
    case "max": return t.params.max(e.bound, e.exclusive);
    case "minLength": return t.params.minLength(e.bound);
    case "maxLength": return t.params.maxLength(e.bound);
    default: return t.params[e.code];
  }
}

function hint(f: ParamField): string | undefined {
  const parts = [
    f.description,
    f.initial !== null && f.kind !== "boolean" ? t.defaultIs(f.initial) : null,
    f.min !== null || f.max !== null ? t.range(f.min === null ? null : String(f.min), f.max === null ? null : String(f.max)) : null,
  ];
  return parts.filter(Boolean).join(" ") || undefined;
}

/** One generated parameter field: control by kind, the schema's hint, and the validation message once shown. */
export function ParamInput({ f, value, error, disabled, onChange }: { f: ParamField; value: string; error: FieldError | undefined; disabled: boolean; onChange: (v: string) => void }) {
  const invalid = error ? true : undefined;
  return (
    <Field label={f.label} required={f.required} hint={hint(f)} error={error ? errorText(error) : undefined}>
      {f.kind === "boolean" ? (
        <select className="select" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
          <option value="true">{t.yes}</option>
          <option value="false">{t.no}</option>
        </select>
      ) : f.kind === "enum" ? (
        <select className="select" value={value} disabled={disabled} aria-invalid={invalid} onChange={(e) => onChange(e.target.value)}>
          {!f.required && <option value="" />}
          {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input className="input" value={value} disabled={disabled} aria-invalid={invalid} inputMode={f.kind === "string" ? "text" : "decimal"} autoComplete="off" onChange={(e) => onChange(e.target.value)} />
      )}
    </Field>
  );
}
