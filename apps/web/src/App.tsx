import { useQuery } from "@tanstack/react-query";
import { CircleAlertIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { meQuery } from "@/lib/session";
import { useTheme } from "@/lib/theme";
import { CockpitPage } from "@/screens/cockpit/cockpit-page";
import { LoginScreen } from "@/screens/login-screen";

/** Garde de route : la coquille n'existe que si `/auth/me` confirme une session ; sinon, le login. */
export function App() {
  const { theme, toggle } = useTheme();
  const me = useQuery(meQuery);

  if (me.isPending) {
    return (
      <main role="status" className="flex min-h-dvh items-center justify-center gap-2 text-muted-foreground">
        <Spinner />
        {fr.session.checking}
      </main>
    );
  }
  if (me.isError) {
    return (
      <main className="flex min-h-dvh items-center justify-center p-4">
        <div className="flex w-full max-w-sm flex-col gap-4">
          <Alert role="alert">
            <CircleAlertIcon />
            <AlertTitle>{fr.session.errorTitle}</AlertTitle>
            <AlertDescription>{fr.session.error}</AlertDescription>
          </Alert>
          <Button type="button" onClick={() => void me.refetch()}>
            {fr.session.retry}
          </Button>
        </div>
      </main>
    );
  }
  if (me.data === null) return <LoginScreen />;
  return <CockpitPage me={me.data} theme={theme} onToggleTheme={toggle} />;
}
