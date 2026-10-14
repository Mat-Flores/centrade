import { fr } from "@/i18n/fr";

import { Empty, PageHead } from "./common";

/** Honest empty state of a screen whose data layer is not wired yet: no figure, nothing assumed. */
export function PendingScreen({ title, note }: { title: string; note?: string }) {
  return (
    <div className="page">
      <PageHead title={title} desc={note} />
      <Empty title={fr.screens.pending} />
    </div>
  );
}
