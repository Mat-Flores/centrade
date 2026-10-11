import { useMutation } from "@tanstack/react-query";
import { CircleAlertIcon, LayoutDashboardIcon, LogOutIcon, MoonIcon, SunIcon } from "lucide-react";
import type { ReactNode } from "react";

import { PersistentBar, type PersistentBarProps } from "@/components/persistent-bar";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { endSession, logout, type Me } from "@/lib/session";
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
const ACTIVE = "cockpit";

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

  return (
    <div className="flex min-h-dvh flex-col">
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

      <div className="flex flex-1 flex-col md:flex-row">
        <nav aria-label={fr.nav.label} className="border-b md:w-60 md:shrink-0 md:border-r md:border-b-0">
          <ul className="flex gap-1 overflow-x-auto p-2 md:flex-col md:overflow-visible md:p-3">
            {SCREENS.map((id) => (
              <li key={id} className="shrink-0">
                <button
                  type="button"
                  disabled={id !== ACTIVE}
                  aria-current={id === ACTIVE ? "page" : undefined}
                  className={cn(
                    "flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-base whitespace-nowrap transition-colors",
                    "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none",
                    id === ACTIVE ? "bg-muted font-semibold" : "text-muted-foreground disabled:cursor-not-allowed",
                  )}
                >
                  {id === ACTIVE && <LayoutDashboardIcon className="size-4 shrink-0" aria-hidden="true" />}
                  <span>{fr.nav.items[id]}</span>
                  {id !== ACTIVE && <span className="ml-auto text-xs">{fr.nav.comingSoon}</span>}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <main className="flex flex-1 flex-col gap-6 p-4 sm:p-6">
          <h1 className="text-2xl font-semibold tracking-tight">{fr.cockpit.title}</h1>
          {signOut.isError && (
            <Alert role="alert">
              <CircleAlertIcon />
              <AlertTitle>{fr.bar.logoutFailedTitle}</AlertTitle>
              <AlertDescription>{fr.bar.logoutFailed}</AlertDescription>
            </Alert>
          )}
          {children ?? (
            <Empty className="min-h-64 border">
              <EmptyHeader>
                <EmptyTitle className="text-base">{fr.cockpit.emptyTitle}</EmptyTitle>
                <EmptyDescription>{fr.cockpit.emptyBody}</EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
        </main>
      </div>
      <footer className="border-t px-4 py-3 text-sm text-muted-foreground sm:px-6">{fr.footer}</footer>
    </div>
  );
}
