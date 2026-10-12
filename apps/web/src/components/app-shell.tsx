import { useMutation } from "@tanstack/react-query";
import { CircleAlertIcon, LayoutDashboardIcon, LogOutIcon, MoonIcon, SunIcon } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

import { PersistentBar, type PersistentBarProps } from "@/components/persistent-bar";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { endSession, logout, type Me } from "@/lib/session";
import { hasNavigated, navigate, SCREEN_PATHS, screenAt, usePathname, type RoutedScreen } from "@/lib/router";
import type { Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const SCREENS = [
  "cockpit",
  "strategies",
  "orders",
  "risk",
  "accounts",
  "flow",
  "agents",
  "signals",
  "journal",
  "settings",
] as const;
const isRouted = (id: (typeof SCREENS)[number]): id is RoutedScreen => id in SCREEN_PATHS;

const NAV_ITEM = cn(
  "flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-base whitespace-nowrap transition-colors",
  "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none",
);

/** Clic simple : navigation sans rechargement. Ctrl, Cmd, Maj ou clic milieu gardent le comportement du lien. */
function onLinkClick(event: React.MouseEvent<HTMLAnchorElement>, path: string) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  navigate(path);
}

// Aucun relevé n'est branché dans ce lot : tout est « inconnu », jamais supposé.
const NOT_OBSERVED: Pick<PersistentBarProps, "mode" | "connections" | "alertCount"> = {
  mode: "unknown",
  connections: { engines: "unknown", bus: "unknown", database: "unknown" },
  alertCount: null,
};

export interface AppShellProps {
  me: Me;
  theme: Theme;
  onToggleTheme: () => void;
  /** Alimentation de la barre persistante (le Cockpit la branche sur l'API). */
  bar?: Partial<PersistentBarProps>;
  /** Contenu de l'écran actif ; état vide soigné par défaut. */
  children?: ReactNode;
}

export function AppShell({ me, theme, onToggleTheme, bar, children }: AppShellProps) {
  const signOut = useMutation({ mutationFn: logout, onSuccess: endSession });
  const ThemeIcon = theme === "dark" ? SunIcon : MoonIcon;
  const pathname = usePathname();
  const active = screenAt(pathname);
  const title = active ? fr.nav.items[active] : fr.routes.notFoundTitle;
  const main = useRef<HTMLElement>(null);

  // Changement d'écran : titre de l'onglet à jour et focus sur le contenu (le lecteur d'écran annonce le titre).
  useEffect(() => {
    document.title = `${title} · ${fr.productName}`;
    if (hasNavigated()) main.current?.focus();
  }, [pathname, title]);

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#contenu"
        className="sr-only focus-visible:not-sr-only focus-visible:absolute focus-visible:top-2 focus-visible:left-2 focus-visible:z-50 focus-visible:rounded-lg focus-visible:border focus-visible:bg-card focus-visible:px-4 focus-visible:py-3 focus-visible:text-base"
      >
        {fr.nav.skip}
      </a>
      <PersistentBar
        {...NOT_OBSERVED}
        {...bar}
        actions={
          <>
            <span className="hidden text-sm text-muted-foreground lg:inline">
              {me.email} ({fr.roles[me.role]})
            </span>
            <Button
              type="button"
              variant="ghost"
              className="size-11 px-0"
              aria-label={theme === "dark" ? fr.bar.theme.toLight : fr.bar.theme.toDark}
              onClick={onToggleTheme}
            >
              <ThemeIcon />
            </Button>
            <Button type="button" variant="outline" disabled={signOut.isPending} onClick={() => signOut.mutate()}>
              {signOut.isPending ? <Spinner data-icon="inline-start" /> : <LogOutIcon data-icon="inline-start" />}
              {signOut.isPending ? fr.bar.loggingOut : fr.bar.logout}
            </Button>
          </>
        }
      />

      <div className="flex flex-1 flex-col lg:flex-row">
        <nav aria-label={fr.nav.label} className="border-b lg:w-60 lg:shrink-0 lg:border-r lg:border-b-0">
          <ul className="flex gap-1 overflow-x-auto p-2 lg:flex-col lg:overflow-visible lg:p-3">
            {SCREENS.map((id) => (
              <li key={id} className="shrink-0">
                {isRouted(id) ? (
                  <a
                    href={SCREEN_PATHS[id]}
                    aria-current={id === active ? "page" : undefined}
                    onClick={(event) => onLinkClick(event, SCREEN_PATHS[id])}
                    className={cn(NAV_ITEM, id === active ? "bg-muted font-semibold" : "hover:bg-muted")}
                  >
                    {id === "cockpit" && <LayoutDashboardIcon className="size-4 shrink-0" aria-hidden="true" />}
                    <span>{fr.nav.items[id]}</span>
                  </a>
                ) : (
                  <button type="button" disabled className={cn(NAV_ITEM, "text-muted-foreground disabled:cursor-not-allowed")}>
                    <span>{fr.nav.items[id]}</span>
                    <span className="ml-auto text-xs">{fr.nav.comingSoon}</span>
                  </button>
                )}
              </li>
            ))}
          </ul>
        </nav>

        <main ref={main} id="contenu" tabIndex={-1} className="flex min-w-0 flex-1 flex-col gap-6 p-4 outline-none sm:p-6">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {signOut.isError && (
            <Alert role="alert">
              <CircleAlertIcon />
              <AlertTitle>{fr.bar.logoutFailedTitle}</AlertTitle>
              <AlertDescription>{fr.bar.logoutFailed}</AlertDescription>
            </Alert>
          )}
          {children}
        </main>
      </div>
      <footer className="border-t px-4 py-3 text-sm text-muted-foreground sm:px-6">{fr.footer}</footer>
    </div>
  );
}
