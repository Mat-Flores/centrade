import { PendingScreen } from "@/app/PendingScreen";
import type { LibraryTab } from "@/app/router";
import { fr } from "@/i18n/fr";

export function Library({ tab }: { tab: LibraryTab }) {
  return <PendingScreen title={fr.nav.library} note={fr.screens.libraryTabs[tab]} />;
}
