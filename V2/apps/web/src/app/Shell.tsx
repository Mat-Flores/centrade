import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { fr } from "@/i18n/fr";
import { useServerNow } from "@/lib/clock";
import { degradation } from "@/lib/cockpit";
import { connectionSummary } from "@/lib/connection";
import { alertsQuery, commandsQuery, healthQuery, instancesQuery } from "@/lib/instances";
import { useAnnouncement } from "@/lib/announce";
import { endSession, logout, type Me } from "@/lib/session";
import { useCockpitStream } from "@/lib/stream";
import { SoonButton } from "@/ui/ui";

import { ColorDialog } from "./ColorDialog";
import { DegradationProvider } from "./degradation";
import { InlineError } from "./common";
import { Link } from "./Link";
import { Menu, type MenuItem } from "./Menu";
import { hasNavigated, href, useRoute, type Route } from "./router";
import { setTheme, useTheme } from "./theme/theme";
import "./app.css";

const NAV: { label: string; to: Route; on: (r: Route) => boolean }[] = [
  { label: fr.nav.instances, to: { page: "instances" }, on: (r) => r.page === "instances" || r.page === "instance" },
  { label: fr.nav.library, to: { page: "library", tab: "keys" }, on: (r) => r.page === "library" },
  { label: fr.nav.journal, to: { page: "journal" }, on: (r) => r.page === "journal" },
  { label: fr.nav.advanced, to: { page: "advanced" }, on: (r) => r.page === "advanced" },
];

const NONE: never[] = []; // a stable empty list: the announcer compares by reference
const initials = (email: string) => email.slice(0, 2).toUpperCase();

/** Top bar, left to right: where I am (navigation), whether it is reachable (connection), the safety command,
 *  then who I am (account, appearance, sign out). Nothing else. */
export function Shell({ me, children }: { me: Me; children: ReactNode }) {
  const route = useRoute();
  const theme = useTheme();
  const [colors, setColors] = useState(false);
  const main = useRef<HTMLElement>(null);
  const signOut = useMutation({ mutationFn: logout, onSuccess: endSession });

  // The cockpit's single stream, opened once here: every screen reads the same cache.
  const instances = useQuery(instancesQuery);
  const commands = useQuery(commandsQuery);
  const alerts = useQuery(alertsQuery);
  const health = useQuery(healthQuery);
  const { silentMs } = useCockpitStream();
  const nowMs = Date.parse(useServerNow());
  const report = health.isError ? undefined : health.data;
  const degraded = degradation({ streamSilentMs: silentMs, health: report, healthFailed: health.isError });
  const conn = connectionSummary(instances.data?.items, degraded, nowMs);
  // Spoken changes (WCAG 4.1.3): observed state, command outcome, alert, degraded mode. A failed alerts read must not mute the rest.
  const announced = useAnnouncement(
    { instances: instances.data?.items ?? NONE, commands: commands.data?.items ?? NONE, alerts: alerts.data?.items ?? NONE, degraded: degraded.degraded },
    instances.isSuccess && commands.isSuccess && (alerts.isSuccess || alerts.isError),
  );

  // Screen change: the content takes the focus (the screen reader announces the title). Never on the first display.
  const page = route.page;
  useEffect(() => {
    if (hasNavigated()) main.current?.focus();
  }, [page]);

  const navItems: MenuItem[] = NAV.map((n) => ({ label: n.label, href: href(n.to), current: n.on(route) }));
  const account: MenuItem[] = [
    { label: theme === "dark" ? fr.shell.themeToLight : fr.shell.themeToDark, hint: fr.shell.appearance, onSelect: () => setTheme(theme === "dark" ? "light" : "dark") },
    { label: fr.shell.colors, hint: fr.shell.customize, onSelect: () => setColors(true) },
    { label: fr.shell.settings, hint: fr.shell.fullPage, href: href({ page: "settings" }), current: route.page === "settings" },
    { label: signOut.isPending ? fr.shell.loggingOut : fr.shell.logout, sep: true, onSelect: () => !signOut.isPending && signOut.mutate() },
  ];

  return (
    <>
      <a href="#contenu" className="sr" onClick={(e) => { e.preventDefault(); main.current?.focus(); }}>{fr.nav.skip}</a>
      <header className="bar">
        <Link className="mark" to={{ page: "instances" }} aria-label={fr.nav.home}><span className="title">{fr.productName}</span></Link>
        <nav className="nav" aria-label={fr.nav.main}>
          {NAV.map((n) => <Link key={n.label} to={n.to} aria-current={n.on(route) ? "page" : undefined}>{n.label}</Link>)}
        </nav>
        <Menu className="nav-menu" label={fr.nav.menu} panelLabel={fr.nav.main} align="left" items={navItems} />
        <span className="spacer" />
        {/* The dot is colored only for what is observed; "Session ouverte" while nothing is loaded. */}
        <Link className={`conn ${conn.tone === "neutral" ? "" : conn.tone}`} to={{ page: "instances" }} data-tip={conn.tip}>
          <i className="conn-dot" aria-hidden="true" /><span>{conn.text}</span>
        </Link>
        <SoonButton variant="danger" small>{fr.shell.emergencyStop}</SoonButton>
        <Menu ghost btnClassName="acct" ariaLabel={fr.shell.account(me.email)} items={account}
          label={<span className="avatar" aria-hidden="true">{initials(me.email)}</span>}
          head={<><b>{me.email}</b><span>{fr.shell.accountRole(fr.roles[me.role])}</span></>} />
      </header>
      <div className="sr" aria-live="polite" aria-atomic="true" data-testid="announcer">{announced}</div>
      <InlineError message={signOut.isError ? fr.shell.logoutFailed : null} />
      <main id="contenu" ref={main} tabIndex={-1} style={{ outline: "none" }}><DegradationProvider value={degraded}>{children}</DegradationProvider></main>
      <ColorDialog open={colors} onClose={() => setColors(false)} />
    </>
  );
}

