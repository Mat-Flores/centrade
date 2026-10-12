import { Badge } from "@/components/ui/badge";
import { fr } from "@/i18n/fr";
import type { Instance } from "@/lib/instances";
import { formatDecimalText } from "@/lib/format";
import type { TradingMode } from "@/lib/trading";
import { attempt, Ts } from "@/screens/accounts/cells";

const t = fr.orders;

/** Décimal en fr-CA, toutes les décimales conservées ; illisible : écrit comme tel, jamais deviné. */
export function num(amount: string | null, signed = false): string {
  if (amount === null) return t.unreadable;
  return attempt(() => formatDecimalText(amount, signed)) ?? t.unreadable;
}

/** Instance d'une ligne : nom, mode de la ligne (paper : « simulé »), jamais un mode supposé. */
export function InstanceCell({ id, mode, instances }: { id: string; mode: TradingMode; instances: ReadonlyMap<string, Instance> }) {
  const name = instances.get(id)?.name;
  return (
    <div className="flex flex-col items-start gap-1">
      <span className="font-mono font-semibold">{name ?? t.unknownInstance}</span>
      <ModeMark mode={mode} />
    </div>
  );
}

export function ModeMark({ mode }: { mode: TradingMode }) {
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <Badge variant={mode === "live" ? "live" : "default"}>{t.modes[mode]}</Badge>
      {mode === "paper" && (
        <span className="text-xs text-muted-foreground" title={t.simulatedHint}>
          {t.simulated}
        </span>
      )}
    </span>
  );
}

export { Ts };
