import { AppShell } from "@/components/app-shell";
import { useShellBar } from "@/components/use-shell-bar";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { fr } from "@/i18n/fr";
import { navigate, SCREEN_PATHS, type RoutedScreen } from "@/lib/router";
import type { Me } from "@/lib/session";
import type { Theme } from "@/lib/theme";
import { Button } from "@/components/ui/button";
import { AccountsScreen } from "./accounts/accounts-screen";

function ComingSoon({ text }: { text: string }) {
  return (
    <Empty className="min-h-56">
      <EmptyHeader>
        <EmptyTitle className="text-base">{fr.routes.soonTitle}</EmptyTitle>
        <EmptyDescription>{text}</EmptyDescription>
        <EmptyDescription>{fr.routes.soonAction}</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button type="button" variant="outline" onClick={() => navigate(SCREEN_PATHS.cockpit)}>
          {fr.routes.toCockpit}
        </Button>
      </EmptyContent>
    </Empty>
  );
}

/**
 * Écrans hors Cockpit, par route. Le lot suivant remplace les deux entrées `ComingSoon`
 * (strategies, orders) par ses écrans ; `me` leur est transmis pour les droits d'écriture.
 */
const SCREENS: Record<Exclude<RoutedScreen, "cockpit">, (me: Me) => React.ReactNode> = {
  strategies: () => <ComingSoon text={fr.routes.soon.strategies} />,
  orders: () => <ComingSoon text={fr.routes.soon.orders} />,
  accounts: (me) => <AccountsScreen isAdmin={me.role === "admin"} />,
};

/** Coquille d'un écran hors Cockpit (ou d'une adresse inconnue) : même barre persistante, même navigation. */
export function ScreenPage({ me, theme, onToggleTheme, screen }: { me: Me; theme: Theme; onToggleTheme: () => void; screen: Exclude<RoutedScreen, "cockpit"> | null }) {
  const { bar } = useShellBar();
  return (
    <AppShell me={me} theme={theme} onToggleTheme={onToggleTheme} bar={bar}>
      {screen ? (
        SCREENS[screen](me)
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
