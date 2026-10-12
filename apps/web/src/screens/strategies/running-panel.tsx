import { ObservedValue } from "@/components/observed-value";
import { TableShell, TD, TH, THEAD } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { fr } from "@/i18n/fr";
import { ENGINE_STALE_MS } from "@/lib/cockpit";
import { shortHash, type InstanceDetail } from "@/lib/strategies";

const t = fr.strategies.running;
const show = (v: unknown): string => (v === undefined ? t.missing : typeof v === "string" ? v : JSON.stringify(v));

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm break-words">{children}</dd>
    </div>
  );
}

/**
 * « Ce qui tourne réellement » (F9, I10) : ce que le moteur rapporte, daté, jamais ce qui a été demandé.
 * Chaque valeur passe par `ObservedValue` (âge, péremption, inconnu). Un écart entre la configuration effective et
 * la configuration générée est mis en évidence : clé, attendu, observé.
 */
export function RunningPanel({ detail, nowIso, dimmed }: { detail: InstanceDetail; nowIso: string; dimmed: boolean }) {
  const eff = detail.effective_config;
  const effective = eff.value;
  const drift = detail.drift;
  const driftRows = drift.value ?? [];
  const driftKeys = new Set(driftRows.map((d) => d.key));
  const version = effective?.engine_version;
  const keys = effective ? Object.keys(effective).filter((k) => k !== "engine_version") : [];
  const rowKeys = [...new Set([...keys, ...driftRows.map((d) => d.key)])].sort();
  const expectedOf = (k: string) => driftRows.find((d) => d.key === k)?.expected;
  const common = { serverTime: nowIso, staleAfterMs: ENGINE_STALE_MS } as const;

  return (
    <section aria-labelledby={`running-${detail.id}`} data-running={detail.name} data-dimmed={dimmed || undefined} className="flex flex-col gap-4 rounded-lg border bg-background p-4">
      <div>
        <h4 id={`running-${detail.id}`} className="text-base font-semibold">{t.title}</h4>
        <p className="text-sm text-muted-foreground">{t.intro}</p>
      </div>

      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
        <Item label={t.fingerprint}>
          {detail.deployment_fingerprint ? (
            <span className="font-mono" title={detail.deployment_fingerprint}>
              {shortHash(detail.deployment_fingerprint, 16)}
            </span>
          ) : (
            <span className="text-muted-foreground">{t.fingerprintNone}</span>
          )}
        </Item>
        <Item label={t.configHash}>
          {detail.config_hash ? (
            <span className="font-mono" title={detail.config_hash}>
              {shortHash(detail.config_hash, 16)}
            </span>
          ) : (
            <span className="text-muted-foreground">{t.fingerprintNone}</span>
          )}
        </Item>
        <Item label={t.engineVersion}>
          <ObservedValue mono value={typeof version === "string" ? version : "unknown"} observedAt={eff.observed_at} {...common} />
        </Item>
        <Item label={t.strategy}>
          {detail.strategy ? (
            <span>
              <span className="font-mono">{detail.strategy.name}</span> v{detail.strategy.version}{" "}
              <span className="font-mono text-muted-foreground" title={detail.strategy.code_hash}>
                {shortHash(detail.strategy.code_hash)}
              </span>
            </span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </Item>
        <Item label={t.account}>{detail.account ? `${detail.account.label} (${detail.account.currency})` : "—"}</Item>
      </dl>

      <div className="flex flex-col gap-2">
        <h5 className="text-sm font-semibold">{t.drift}</h5>
        {drift.value === null ? (
          <ObservedValue value="unknown" observedAt={null} {...common} />
        ) : driftRows.length === 0 ? (
          <ObservedValue value={t.driftNone} observedAt={drift.observed_at} {...common} />
        ) : (
          <div data-drift className="flex flex-col gap-2">
            <p className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant="danger">{t.driftBadge}</Badge>
              <span className="font-medium">{t.driftHint}</span>
            </p>
            <ObservedValue
              value={
                <ul className="flex flex-col gap-1">
                  {driftRows.map((d) => (
                    <li key={d.key} data-drift-key={d.key} className="grid grid-cols-1 gap-x-4 rounded-md bg-muted px-3 py-2 sm:grid-cols-3">
                      <span className="font-mono font-semibold">{d.key}</span>
                      <span>
                        {t.driftColumns.expected} : <span className="font-mono">{show(d.expected)}</span>
                      </span>
                      <span>
                        {t.driftColumns.observed} : <span className="font-mono font-semibold">{show(d.observed)}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              }
              observedAt={drift.observed_at}
              {...common}
            />
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <h5 className="text-sm font-semibold">{t.effective}</h5>
        {effective === null ? (
          <div className="flex flex-col gap-1">
            <ObservedValue value="unknown" observedAt={null} {...common} />
            <p className="text-sm text-muted-foreground">{t.effectiveUnknown}</p>
          </div>
        ) : (
          <>
            <p className="text-sm">
              <ObservedValue value={fr.observed.observedAt} observedAt={eff.observed_at} {...common} />
            </p>
            <TableShell label={t.effective} minWidth="min-w-[28rem]" dimmed={dimmed}>
              <thead className={THEAD}>
                <tr>
                  <th scope="col" className={TH}>{t.columns.key}</th>
                  <th scope="col" className={TH}>{t.columns.effective}</th>
                  <th scope="col" className={TH}>{t.columns.expected}</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {rowKeys.map((k) => (
                  <tr key={k} data-config-key={k} data-drift-row={driftKeys.has(k) || undefined} className={driftKeys.has(k) ? "bg-muted" : undefined}>
                    <th scope="row" className={`${TD} text-left font-mono font-normal`}>{k}</th>
                    <td className={`${TD} font-mono ${driftKeys.has(k) ? "font-semibold" : ""}`}>{show(effective[k])}</td>
                    <td className={`${TD} font-mono`}>{driftKeys.has(k) ? show(expectedOf(k)) : <span className="text-muted-foreground">=</span>}</td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
          </>
        )}
      </div>
    </section>
  );
}
