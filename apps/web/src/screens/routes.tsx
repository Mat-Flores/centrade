import { AppShell } from "@/components/app-shell";
import { useShellBar } from "@/components/use-shell-bar";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { fr } from "@/i18n/fr";
import { navigate, SCREEN_PATHS, type RoutedScreen } from "@/lib/router";
import type { Me } from "@/lib/session";
import type { Theme } from "@/lib/theme";
import { Button } from "@/components/ui/button";
import type { Instance } from "@/lib/instances";
import { AccountsScreen } from "./accounts/accounts-screen";
import { OrdersScreen } from "./orders/orders-screen";
import { StrategiesScreen } from "./strategies/strategies-screen";

/** Ce que la coquille partage avec chaque écran : un seul flux et une seule horloge pour toute l'application. */
export interface ScreenContext {
  me: Me;
  /** Mode dégradé : seules les actions qui réduisent le risque restent actives. */
  degraded: boolean;
  nowIso: string;
  instances: Instance[] | undefined;
}

/** Écrans hors Cockpit, par route. */
const SCREENS: Record<Exclude<RoutedScreen, "cockpit">, (ctx: ScreenContext) => React.ReactNode> = {
  strategies: ({ me, degraded, nowIso, instances }) => (
    <StrategiesScreen canAct={me.role !== "viewer"} isAdmin={me.role === "admin"} degraded={degraded} nowIso={nowIso} instances={instances} />
  ),
  orders: ({ me, degraded, nowIso, instances }) => (
    <OrdersScreen canAct={me.role !== "viewer"} degraded={degraded} nowIso={nowIso} instances={instances} />
  ),
  accounts: ({ me }) => <AccountsScreen isAdmin={me.role === "admin"} />,
};

/** Coquille d'un écran hors Cockpit (ou d'une adresse inconnue) : même barre persistante, même navigation. */
export function ScreenPage({ me, theme, onToggleTheme, screen }: { me: Me; theme: Theme; onToggleTheme: () => void; screen: Exclude<RoutedScreen, "cockpit"> | null }) {
  const { bar, degraded, nowIso, items } = useShellBar();
  return (
    <AppShell me={me} theme={theme} onToggleTheme={onToggleTheme} bar={bar}>
      {screen ? (
        SCREENS[screen]({ me, degraded: degraded.degraded, nowIso, instances: items })
      ) : (
        <Empty className="min-h-56">
          <EmptyHeader>
            <EmptyTitle className="text-base">{fr.routes.notFoundTitle}</EmptyTitle>
            <EmptyDescription>{fr.routes.notFound}</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button type="button" variant="outline" onClick={() => navigate(SCREEN_PATHS.cockpit)}>
              {fr.routes.toCockpit}
            </Button>
          </EmptyContent>
        </Empty>
      )}
    </AppShell>
  );
}
