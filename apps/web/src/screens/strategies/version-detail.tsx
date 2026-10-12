import { shiftDecimal } from "@/lib/decimal";
import { fr } from "@/i18n/fr";
import { formatDecimalText } from "@/lib/format";
import type { VersionDetailSchema } from "@/lib/strategies";
import type { z } from "zod";
import { attempt, Ts } from "@/screens/accounts/cells";

const t = fr.strategies.detail;
type Detail = z.infer<typeof VersionDetailSchema>;
type Raw = Record<string, unknown>;

const rec = (v: unknown): Raw => (typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Raw) : {});
const list = (v: unknown): string => (Array.isArray(v) && v.length > 0 ? v.map(String).join(", ") : t.none);
const dec = (v: unknown, signed = false): string => (typeof v === "string" ? (attempt(() => formatDecimalText(v, signed)) ?? v) : v == null ? t.none : String(v));

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="font-mono text-sm break-words">{children}</dd>
    </div>
  );
}

/** Ratio décimal (« -0.05 ») avec son équivalent en pourcentage, sans arrondi. */
function Ratio({ value }: { value: unknown }) {
  if (typeof value !== "string") return <>{t.none}</>;
  const pct = attempt(() => shiftDecimal(value, 2));
  return (
    <>
      {dec(value, true)}
      {pct !== null && <span className="font-sans text-muted-foreground"> ({dec(pct, true)} %)</span>}
    </>
  );
}

export function ManifestView({ manifest }: { manifest: Raw }) {
  const sizing = rec(manifest.sizing);
  const risk = Object.entries(rec(manifest.risk_defaults));
  const params = Object.keys(rec(rec(manifest.params_schema).properties));
  const f = t.fields;
  return (
    <section aria-labelledby="manifest-title" className="flex flex-col gap-3">
      <h4 id="manifest-title" className="text-base font-semibold">{t.manifest}</h4>
      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
        <Row label={f.entrypoint}>{String(manifest.entrypoint ?? t.none)}</Row>
        <Row label={f.asset_classes}>{list(manifest.asset_classes)}</Row>
        <Row label={f.trading_mode}>{String(manifest.trading_mode ?? t.none)}</Row>
        <Row label={f.timeframes}>{list(manifest.timeframes)}</Row>
        <Row label={f.modes}>{list(manifest.modes)}</Row>
        <Row label={f.requires_data}>{list(manifest.requires_data)}</Row>
        <Row label={f.stake}>{dec(sizing.stake_amount)}</Row>
        <Row label={f.maxOpen}>{String(sizing.max_open_positions ?? t.none)}</Row>
        <Row label={f.riskDefaults}>{risk.length ? risk.map(([k, v]) => `${k} : ${dec(v)}`).join(" ; ") : t.none}</Row>
        <Row label={f.params}>{params.length ? params.join(", ") : t.none}</Row>
      </dl>
    </section>
  );
}

/** Politique de sortie déclarée (F10) : ce que la plateforme écrit dans la configuration du moteur. */
export function ExitPolicy({ exits }: { exits: Raw }) {
  const e = t.exits;
  const trailing = Object.entries(rec(exits.trailing));
  const targets = Object.entries(rec(exits.take_profit));
  return (
    <section aria-labelledby="exits-title" className="flex flex-col gap-3" data-exits>
      <h4 id="exits-title" className="text-base font-semibold">{e.title}</h4>
      <p className="max-w-3xl text-sm text-muted-foreground">{e.intro}</p>
      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 xl:grid-cols-4">
        <Row label={e.stoploss}>
          <Ratio value={exits.stoploss} />
        </Row>
        <Row label={e.trailing}>{trailing.length ? trailing.map(([k, v]) => `${k} : ${typeof v === "string" ? dec(v) : String(v)}`).join(" ; ") : t.none}</Row>
        <Row label={e.takeProfit}>{targets.length ? targets.map(([m, g]) => e.targetAfter(m, dec(g, true))).join(" ; ") : t.none}</Row>
        <Row label={e.venue}>{exits.stop_on_venue === true ? e.yes : e.no}</Row>
      </dl>
    </section>
  );
}

export function StaticChecks({ checks, serverTime }: { checks: Raw; serverTime: string }) {
  const errors = Array.isArray(checks.errors) ? checks.errors.map(String) : [];
  const ok = checks.ok === true && errors.length === 0;
  return (
    <section aria-labelledby="checks-title" className="flex flex-col gap-2">
      <h4 id="checks-title" className="text-base font-semibold">{t.checks.title}</h4>
      <p className="text-sm">
        <span className="font-semibold">{ok ? t.checks.ok : t.checks.failed}</span>
        {typeof checks.checked_at === "string" && (
          <span className="text-muted-foreground">
            {" "}
            · {t.checks.at} <Ts iso={checks.checked_at} serverTime={serverTime} />
          </span>
        )}
      </p>
      {errors.length > 0 && (
        <ul className="flex list-disc flex-col gap-1 pl-5 font-mono text-sm">
          {errors.map((m, n) => (
            <li key={n}>{m}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function CodeView({ code }: { code: string }) {
  return (
    <details className="rounded-lg border">
      <summary className="flex min-h-11 cursor-pointer items-center px-3 text-base font-medium focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
        {t.code.title} <span className="ml-2 text-sm font-normal text-muted-foreground">({t.code.lines(code.split("\n").length)})</span>
      </summary>
      <pre tabIndex={0} aria-label={t.code.title} className="max-h-96 overflow-auto border-t bg-muted p-3 font-mono text-sm">
        {code}
      </pre>
    </details>
  );
}

export type { Detail };
