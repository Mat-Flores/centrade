import { useEffect } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useStore } from "../data/store";
import { useRoute, type Route } from "./route";
import { Shell } from "./Shell";
import { useTheme } from "./theme";
import { applyColors } from "../theme/colors";
import { Instances } from "../screens/Instances";
import { InstanceScreen } from "../screens/instance/InstanceScreen";
import { Bibliotheque } from "../screens/Bibliotheque";
import { Journal } from "../screens/Journal";
import { Avance } from "../screens/Avance";
import { Parametres } from "../screens/Parametres";

const TITLE: Record<Route["page"], string> = {
  instances: "Instances", instance: "Instance", bibliotheque: "Bibliothèque", journal: "Journal", avance: "Avancé", parametres: "Paramètres",
};

function Screen({ route }: { route: Route }) {
  switch (route.page) {
    case "instances": return <Instances />;
    case "instance": return <InstanceScreen id={route.id} tab={route.tab} />;
    case "bibliotheque": return <Bibliotheque tab={route.tab} />;
    case "journal": return <Journal />;
    case "avance": return <Avance />;
    case "parametres": return <Parametres />;
  }
}

export function App() {
  const route = useRoute();
  const theme = useTheme();
  const colors = useStore((s) => s.colors);
  const instName = useStore((s) => (route.page === "instance" ? s.instances.find((i) => i.id === route.id)?.name : undefined));
  const reduce = useReducedMotion();

  useEffect(() => { document.documentElement.lang = "fr"; }, []);
  useEffect(() => { document.documentElement.dataset.theme = theme; applyColors(colors); }, [colors, theme]);
  useEffect(() => { document.title = `${route.page === "instance" ? instName ?? "Instance" : TITLE[route.page]} · Centrade`; }, [route, instName]);

  // Un changement d'onglet dans une instance n'est pas un changement d'écran.
  const key = route.page === "instance" ? `instance/${route.id}` : route.page === "bibliotheque" ? "bibliotheque" : route.page;
  return (
    <Shell>
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
