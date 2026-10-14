import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect } from "react";

import { LoginScreen } from "@/features/auth/LoginScreen";
import { Advanced } from "@/features/advanced/Advanced";
import { Instances } from "@/features/instances/Instances";
import { Journal } from "@/features/journal/Journal";
import { Library } from "@/features/library/Library";
import { Settings } from "@/features/settings/Settings";
import { fr } from "@/i18n/fr";
import { meQuery, type Me } from "@/lib/session";
import { Button } from "@/ui/ui";

import { NotFound } from "./NotFound";
import { href, replace, useRoute, type Route } from "./router";
import { Shell } from "./Shell";

const TITLE: Record<Route["page"], string> = {
  instances: fr.nav.instances, instance: fr.nav.instance, library: fr.nav.library, journal: fr.nav.journal,
  advanced: fr.nav.advanced, settings: fr.nav.settings, notFound: fr.nav.notFoundTitle,
};

function Screen({ route }: { route: Route }) {
  switch (route.page) {
    case "instances":
    case "instance": return <Instances />;
    case "library": return <Library tab={route.tab} />;
    case "journal": return <Journal />;
    case "advanced": return <Advanced />;
    case "settings": return <Settings />;
    case "notFound": return <NotFound />;
  }
}

function Centered({ children, role }: { children: React.ReactNode; role?: "status" | "alert" }) {
  return <main role={role} style={{ minHeight: "100dvh", display: "grid", placeItems: "center", alignContent: "center", gap: 16, padding: 16, textAlign: "center" }}>{children}</main>;
}

/** Content of a signed-in session: the shell and the screen of the route, with the motion of the mockup. */
function Session({ me }: { me: Me }) {
  const route = useRoute();
  const reduce = useReducedMotion();

  // Canonical address (`/` and `/library` included) without a new history step.
  useEffect(() => {
    if (route.page !== "notFound" && window.location.pathname !== href(route)) replace(href(route));
  }, [route]);

  // A tab change inside an instance is not a screen change.
  const key = route.page === "instance" ? `instance/${route.id}` : route.page;
  return (
    <Shell me={me}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={key}
          initial={reduce ? false : { opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduce ? { opacity: 1 } : { opacity: 0 }}
          transition={reduce ? { duration: 0 } : { duration: 0.16, ease: [0.2, 0.8, 0.2, 1] }}
        >
          <Screen route={route} />
        </motion.div>
      </AnimatePresence>
    </Shell>
  );
}

/** Session guard: the shell exists only if `/auth/me` confirms a session; otherwise the login. */
export function App() {
  const me = useQuery(meQuery);
  const route = useRoute();
  const signedIn = me.data != null;

  useEffect(() => { document.documentElement.lang = "fr"; }, []);
  // Tab title follows the screen (the instance name comes with the instance screen).
  useEffect(() => {
    const title = me.isPending ? fr.productName : signedIn ? TITLE[route.page] : fr.nav.login;
    document.title = title === fr.productName ? title : `${title} · ${fr.productName}`;
  }, [me.isPending, signedIn, route.page]);

  if (me.isPending) return <Centered role="status">{fr.session.checking}</Centered>;
  if (me.isError) {
    return (
      <Centered role="alert">
        <strong>{fr.session.errorTitle}</strong>
        <p style={{ margin: 0, maxWidth: 420 }}>{fr.session.error}</p>
        <Button onClick={() => void me.refetch()}>{fr.session.retry}</Button>
      </Centered>
    );
  }
  if (me.data === null) return <LoginScreen />;
  return <Session me={me.data} />;
}
