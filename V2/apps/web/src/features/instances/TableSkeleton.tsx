import { fr } from "@/i18n/fr";
import { SectionHead } from "@/app/common";
import { Panel } from "@/ui/ui";

/** Honest loading state: grey bars, no figure. */
export function TableSkeleton({ title }: { title: string }) {
  return (
    <section aria-label={title} aria-busy="true">
      <SectionHead title={title} />
      <Panel>
        <div role="status" aria-label={fr.instances.loading} className="skel-rows">
          {[0, 1].map((n) => <div key={n} className="skel" />)}
        </div>
      </Panel>
    </section>
  );
}
