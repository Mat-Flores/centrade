import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { fr } from "@/i18n/fr";
import { permissionState, type Account, type Key, type KeyUsage } from "@/lib/accounts";
import { formatAge, formatTimestamp } from "@/lib/format";

const t = fr.accounts;

/** Texte calculé, ou `null` si la donnée est illisible (le format lève sur une date ou un montant invalide). */
export function attempt(fn: () => string): string | null {
  try {
    return fn();
  } catch {
    return null;
  }
}

/** Horodatage en heure de Toronto, fuseau indiqué, avec l'âge d'après l'heure du serveur. Illisible : écrit tel quel. */
export function Ts({ iso, serverTime, age = false }: { iso: string; serverTime: string; age?: boolean }) {
  const text = attempt(() => formatTimestamp(iso));
  if (text === null) return <span className="text-muted-foreground">{t.unreadableDate}</span>;
  const ageMs = Date.parse(serverTime) - Date.parse(iso);
  return (
    <time dateTime={iso} className="font-mono">
      {text}
      {age && Number.isFinite(ageMs) && <span className="font-sans text-muted-foreground"> ({formatAge(ageMs)})</span>}
    </time>
  );
}

function KeyLine({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap gap-x-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** État d'une clé : présente ou absente, dates de dépôt, de rotation et de dernier usage. Jamais la valeur. */
export function KeyCell({
  account,
  usage,
  serverTime,
  canWrite,
  onAction,
}: {
  account: Account;
  usage: KeyUsage;
  serverTime: string;
  canWrite: boolean;
  onAction: (mode: "put" | "rotate") => void;
}) {
  const key: Key | null = usage === "trade" ? account.trade_key : account.read_key;
  const name = `${usage === "trade" ? t.columns.tradeKey : t.columns.readKey} — ${account.label}`;
  return (
    <div className="flex flex-col gap-2">
      {key ? (
        <>
          <p className="font-semibold">
            {t.key.present} <span className="font-normal text-muted-foreground">({t.key.version(key.key_version)})</span>
          </p>
          <dl className="flex flex-col gap-0.5 text-sm">
            <KeyLine label={t.key.stored}>
              <Ts iso={key.stored_at} serverTime={serverTime} />
            </KeyLine>
            <KeyLine label={t.key.rotated}>
              {key.rotated_at ? <Ts iso={key.rotated_at} serverTime={serverTime} /> : t.key.none}
            </KeyLine>
            <KeyLine label={t.key.used}>
              {key.last_used_at ? <Ts iso={key.last_used_at} serverTime={serverTime} /> : t.key.never}
            </KeyLine>
          </dl>
        </>
      ) : (
        <p className="font-semibold text-muted-foreground">{t.key.absent}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {key ? (
          <>
            <Button type="button" variant="outline" disabled={!canWrite} aria-label={`${t.key.replace} : ${name}`} onClick={() => onAction("put")}>
              {t.key.replace}
            </Button>
            <Button type="button" variant="outline" disabled={!canWrite} aria-label={`${t.key.rotate} : ${name}`} onClick={() => onAction("rotate")}>
              {t.key.rotate}
            </Button>
          </>
        ) : (
          <Button type="button" variant="outline" disabled={!canWrite} aria-label={`${t.key.deposit} : ${name}`} onClick={() => onAction("put")}>
            {t.key.deposit}
          </Button>
        )}
      </div>
    </div>
  );
}

export function PermissionCell({ account, serverTime }: { account: Account; serverTime: string }) {
  const state = permissionState(account);
  switch (state.kind) {
    case "none":
      return <span className="text-muted-foreground">{t.permissions.none}</span>;
    case "no-key":
      return <span className="text-muted-foreground">{t.permissions.noKey}</span>;
    case "verified":
      return (
        <p>
          <span className="font-semibold">{t.permissions.verified}</span> le <Ts iso={state.at} serverTime={serverTime} age />
        </p>
      );
    case "unverified":
      return (
        <div className="flex flex-col gap-1">
          <Badge variant="unknown">{t.permissions.unverified}</Badge>
          <p className="text-sm text-muted-foreground">{t.permissions.unverifiedHint}</p>
        </div>
      );
  }
}

export function IpCell({ account }: { account: Account }) {
  if (account.type === "paper") return <span className="text-muted-foreground">{t.ip.none}</span>;
  if (account.ip_restricted === null) return <Badge variant="unknown">{t.ip.unknown}</Badge>;
  return account.ip_restricted ? (
    <span className="font-semibold">{t.ip.yes}</span>
  ) : (
    <div className="flex flex-col gap-1">
      <span className="font-semibold">{t.ip.no}</span>
      <p className="text-sm text-muted-foreground">{t.ip.noHint}</p>
    </div>
  );
}
